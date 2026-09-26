// Deployment pipeline for sample-api.
//
// The shape that matters: the contract gate runs BEFORE the registry push, so
// an unacknowledged breaking change never produces a deployable artifact. The
// demo is not "the console turned red" — it is that localhost:8080 is still
// serving the previous version afterwards.
//
// A breaking change is not automatically the end of the build. api-guard pauses
// its review and this pipeline waits for a named human to approve or reject it.
// Three top-level stages, because of where the waiting happens:
//
//   Build and gate  (agent)     checks run; a blocked build saves its review
//   Approval        (no agent)  Jenkins waits; no executor is held meanwhile
//   Ship            (agent)     records the sign-off, then publishes and deploys
//
// A pipeline with one top-level agent would hold an executor for the whole
// wait, which is the exact problem the paused review exists to avoid.
//
// api-guard is pulled from Docker Hub, not built here. sample-api contains no
// api-guard source at all, which is what makes the reusability claim testable
// rather than a matter of trust.

pipeline {
  agent none

  environment {
    DOCKERHUB_USER = 'sohanbhadalkar'
    APP_IMAGE      = "${DOCKERHUB_USER}/sample-api"
    TEST_STACK     = 'docker-compose.yml'
    STAGING_STACK  = 'docker-compose.staging.yml'
    // Jenkins talks to the host's Docker daemon through the mounted socket, so
    // every container it starts is a SIBLING, not a child. Volume paths in
    // `docker run` are therefore resolved by the host — and the workspace lives
    // inside a named volume, so `-v $(pwd):/work` mounts a path the host does
    // not have and the container sees an empty directory. The symptom is a
    // baffling "cannot read config api-guard.yaml: No such file or directory"
    // for a file that is plainly there in the workspace.
    //
    // --volumes-from gives the sibling Jenkins' own volumes at the same paths,
    // so $(pwd) means the same thing in both.
    JENKINS_CONTAINER = 'jenkins-local'
    // TAG, GUARD_IMAGE, GUARD_PULL and APPROVAL_HOURS are set in the Checkout
    // stage, not here. With `agent none` this block is evaluated before any
    // node exists: there is no commit to read and no node environment to
    // consult, so values computed here silently fall back to their defaults.
  }

  options {
    timestamps()
    // Ship reuses the workspace Build and gate left behind: the saved review
    // and the reports live there. A second build running meanwhile would
    // overwrite them, so builds queue instead.
    disableConcurrentBuilds()
    // Checkout happens once, explicitly. A default checkout on the Ship agent
    // would be redundant at best.
    skipDefaultCheckout()
  }

  stages {

    stage('Build and gate') {
      agent any
      // The work is bounded. The approval wait below deliberately is not
      // covered by this, or a pipeline-wide timeout would abort it.
      options { timeout(time: 30, unit: 'MINUTES') }

      stages {

        stage('Checkout') {
          steps {
            checkout scm
            // The gate compares against origin/main. A shallow clone does not have
            // it, and the failure surfaces as a confusing "no spec at origin/main".
            sh 'git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main || true'
            script {
              // Short SHA is the artifact identity: every deploy is traceable to
              // one commit, and a rollback names an exact build rather than "the
              // last one".
              env.TAG = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()

              // The -ai variant: `review` and `approve` need LangGraph. The
              // verdict is the same as the plain image's; only the approval flow
              // is added. API_GUARD_IMAGE / API_GUARD_PULL on the node let a local
              // Jenkins use an image it built itself. Read through the shell,
              // because that is where node environment variables are reliably
              // visible.
              env.GUARD_IMAGE = sh(script: 'echo "${API_GUARD_IMAGE:-sohanbhadalkar/api-guard:1-ai}"', returnStdout: true).trim()
              env.GUARD_PULL = sh(script: 'echo "${API_GUARD_PULL:-true}"', returnStdout: true).trim()
              env.APPROVAL_HOURS = sh(script: 'echo "${API_GUARD_APPROVAL_HOURS:-24}"', returnStdout: true).trim()
              echo "api-guard image: ${env.GUARD_IMAGE} (pull: ${env.GUARD_PULL}), approval window: ${env.APPROVAL_HOURS}h"
            }
          }
        }

        stage('Build app image') {
          steps {
            sh "docker build -t ${APP_IMAGE}:${TAG} ."
          }
        }

        stage('Generate spec') {
          // Runs inside the APP's image, not api-guard's. api-guard deliberately
          // carries no project dependencies — running a FastAPI export script in
          // it fails with ModuleNotFoundError, because FastAPI belongs to the
          // application's environment. Project commands run in the project's
          // environment; the tool only compares the result.
          steps {
            sh """
              docker run --rm --volumes-from ${JENKINS_CONTAINER} -w /app ${APP_IMAGE}:${TAG} \
                python scripts/export_openapi.py --output \$(pwd)/generated.yaml
            """
          }
        }

        stage('Start test API') {
          steps {
            sh "docker compose -f ${TEST_STACK} up -d --build"
          }
        }

        stage('Contract gate') {
          steps {
            script {
              // Join the test stack's network so the API is reachable by service
              // name. Inside a container 'localhost' is the container itself.
              def network = sh(
                script: "docker inspect sample-api-test --format '{{range \$k,\$v := .NetworkSettings.Networks}}{{\$k}}{{end}}'",
                returnStdout: true
              ).trim()

              if (GUARD_PULL == 'true') {
                sh "docker pull ${GUARD_IMAGE}"
              }

              // Reports and review state from an earlier build in this workspace
              // must not be mistaken for this one's.
              sh 'rm -rf api-guard-report .api-guard'

              // `review` is `check` plus the approval workflow: same checks, same
              // exit code. The review id is the build number, so the sign-off in
              // review.md names the build it belongs to.
              def code = _withOptionalGroqKey {
                sh(returnStatus: true, script: """
                  docker run --rm --network ${network} -e GROQ_API_KEY \
                    --volumes-from ${JENKINS_CONTAINER} -w \$(pwd) ${GUARD_IMAGE} \
                    review --config api-guard.yaml \
                           --generated-spec generated.yaml \
                           --url http://api:8000 \
                           --id ${BUILD_NUMBER}
                """)
              }

              // 1 and 2 mean different things and are never collapsed. Only a
              // contract violation can be approved; a tooling error established
              // nothing, so there is nothing to sign off.
              if (code == 0) {
                env.GATE = 'passed'
              } else if (code == 1 && fileExists('api-guard-report/approval-request.md')) {
                env.GATE = 'awaiting-approval'
                env.APPROVAL_QUESTION = readFile('api-guard-report/approval-request.md').trim()
              } else if (code == 1) {
                error('api-guard: the contract would break consumers, and no review could be started to approve it.')
              } else {
                error("api-guard could not reach a conclusion (exit ${code}): config or tooling problem, not a contract violation.")
              }
            }
          }
        }
      }

      post {
        always {
          // The ephemeral stack goes; staging stays running on purpose.
          sh "docker compose -f ${TEST_STACK} down -v || true"

          junit allowEmptyResults: true, testResults: 'api-guard-report/junit.xml'
          // The MCP server reads result.json from these archived artifacts, which
          // is why no separate result storage is needed.
          archiveArtifacts artifacts: 'api-guard-report/**', allowEmptyArchive: true

          script {
            if (fileExists('api-guard-report/report.md')) {
              echo readFile('api-guard-report/report.md')
            }
          }
        }
      }
    }

    stage('Approval') {
      when { expression { env.GATE == 'awaiting-approval' } }
      // No agent. The build sits in the queue view as "waiting for input" and
      // its state is Jenkins' to keep; it survives a controller restart.
      steps {
        script {
          try {
            timeout(time: APPROVAL_HOURS as Integer, unit: 'HOURS') {
              def answer = input(
                id: 'ContractApproval',
                message: "Breaking API change.\n\n${env.APPROVAL_QUESTION}",
                ok: 'Approve and ship',
                submitterParameter: 'SUBMITTER',
                parameters: [
                  string(
                    name: 'APPROVED_BY',
                    defaultValue: '',
                    description: 'Your name, recorded in review.md. Required: an approval nobody signed is not an approval.'
                  ),
                ]
              )
              def name = (answer.APPROVED_BY ?: '').trim()
              if (!name) {
                error('Approval needs a name in APPROVED_BY. Nothing was shipped.')
              }
              env.APPROVED_BY = name
              echo "Approved by ${name} (Jenkins user: ${answer.SUBMITTER})"
            }
          } catch (org.jenkinsci.plugins.workflow.steps.FlowInterruptedException rejected) {
            // Abort in the input dialog, or the timeout elapsing. Either way no
            // human signed off, so this is a failed build, not an aborted one.
            currentBuild.result = 'FAILURE'
            error("Breaking change not approved (rejected, or no answer within ${APPROVAL_HOURS}h). Nothing was shipped.")
          }
        }
      }
    }

    stage('Ship') {
      agent any
      options { timeout(time: 30, unit: 'MINUTES') }

      stages {

        stage('Record approval') {
          when { expression { env.GATE == 'awaiting-approval' } }
          steps {
            // The name reaches the shell as an environment variable, never
            // interpolated into the script, since it is free text from a form.
            withEnv(["APPROVER=${env.APPROVED_BY}"]) {
              sh '''
                docker run --rm -e APPROVER \
                  --volumes-from "$JENKINS_CONTAINER" -w "$(pwd)" "$GUARD_IMAGE" \
                  approve "$BUILD_NUMBER" --by "$APPROVER"
              '''
            }
            archiveArtifacts artifacts: 'api-guard-report/review.md'
            echo readFile('api-guard-report/review.md')
          }
        }

        // Everything below here only runs because the gate passed or a named
        // human approved the breaking change.

        stage('Publish image') {
          // Skipped when no `dockerhub` credential is configured. A fork, or a
          // fresh clone on somebody else's machine, should still be able to run
          // the gate and see it work without first being made to set up a
          // registry account. The contract check is the point; publishing is what
          // happens once it passes.
          steps {
            script {
              if (!_hasCredential('dockerhub')) {
                echo 'No `dockerhub` credential configured - skipping publish and deploy.'
                echo 'Add a Username/password credential with ID `dockerhub` to enable them.'
                env.SKIP_DEPLOY = 'true'
                return
              }
              withCredentials([usernamePassword(
                credentialsId: 'dockerhub',
                usernameVariable: 'DH_USER',
                passwordVariable: 'DH_PASS'
              )]) {
                sh 'echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin'
                sh "docker push ${APP_IMAGE}:${TAG}"
                if (env.BRANCH_NAME == 'main' || env.GIT_BRANCH?.endsWith('main')) {
                  sh "docker tag ${APP_IMAGE}:${TAG} ${APP_IMAGE}:latest"
                  sh "docker push ${APP_IMAGE}:latest"
                }
              }
            }
          }
        }

        stage('Deploy to staging') {
          when { expression { env.SKIP_DEPLOY != 'true' } }
          steps {
            script {
              // Record what is currently live BEFORE replacing it. Working this
              // out after a failed deploy is too late — the thing that knew has
              // already been overwritten.
              env.PREVIOUS_IMAGE = sh(
                script: "docker inspect sample-api-staging --format '{{.Config.Image}}' 2>/dev/null || echo ''",
                returnStdout: true
              ).trim()
              echo "Currently live: ${env.PREVIOUS_IMAGE ?: '(nothing deployed yet)'}"

              sh """
                SAMPLE_API_IMAGE=${APP_IMAGE}:${TAG} docker compose -f ${STAGING_STACK} pull
                SAMPLE_API_IMAGE=${APP_IMAGE}:${TAG} docker compose -f ${STAGING_STACK} up -d
              """
            }
          }
        }

        stage('Smoke test staging') {
          when { expression { env.SKIP_DEPLOY != 'true' } }
          steps {
            script {
              // Poll rather than sleep: a fixed sleep is either too short and
              // flaky, or too long and wastes every build.
              sh '''
                for i in $(seq 1 30); do
                  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
                    echo "staging is up"; exit 0
                  fi
                  sleep 2
                done
                echo "staging did not become healthy within 60s"; exit 1
              '''

              // Re-run the contract check against what is actually deployed. Same
              // tool, same spec, different target — the build passing does not by
              // itself prove the thing that shipped honours the contract.
              //
              // --only conformance, deliberately. Freshness was settled during the
              // build and cannot be re-asked here: the deployed container holds no
              // project dependencies, so the generator would not run. Breaking is a
              // question about two spec files and has nothing to do with what is
              // deployed. Only conformance means anything against a live instance.
              try {
                sh """
                  docker run --rm --add-host=host.docker.internal:host-gateway \
                    --volumes-from ${JENKINS_CONTAINER} -w \$(pwd) ${GUARD_IMAGE} \
                    check --config api-guard.yaml \
                          --only conformance \
                          --url http://host.docker.internal:8080
                """
              } catch (err) {
                if (env.PREVIOUS_IMAGE) {
                  echo "Smoke test failed. Rolling back to ${env.PREVIOUS_IMAGE}"
                  sh """
                    SAMPLE_API_IMAGE=${env.PREVIOUS_IMAGE} docker compose -f ${STAGING_STACK} up -d
                  """
                } else {
                  echo "Smoke test failed and there is no previous version to roll back to."
                }
                throw err
              }
            }
          }
        }
      }
    }
  }

  post {
    failure {
      echo 'Contract gate, approval or smoke test failed. Nothing new was deployed.'
    }
  }
}

/** True when a credential with this ID exists, without throwing if it does not. */
boolean _hasCredential(String id) {
  try {
    withCredentials([usernamePassword(
      credentialsId: id, usernameVariable: 'U', passwordVariable: 'P'
    )]) { }
    return true
  } catch (ignored) {
    return false
  }
}

/**
 * Runs the body with GROQ_API_KEY bound when a `groq-api-key` secret-text
 * credential exists. Without it the advisory band is "unknown" and nothing
 * else changes — the gate never depends on the model.
 */
def _withOptionalGroqKey(Closure body) {
  try {
    withCredentials([string(credentialsId: 'groq-api-key', variable: 'GROQ_API_KEY')]) {
      return body()
    }
  } catch (org.jenkinsci.plugins.credentialsbinding.impl.CredentialNotFoundException missing) {
    return body()
  }
}
