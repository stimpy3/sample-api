// Deployment pipeline for sample-api.
//
// The shape that matters: the contract gate runs BEFORE the registry push, so
// an unacknowledged breaking change never produces a deployable artifact. The
// demo is not "the console turned red" — it is that localhost:8080 is still
// serving the previous version afterwards.
//
// api-guard is pulled from Docker Hub, not built here. sample-api contains no
// api-guard source at all, which is what makes the reusability claim testable
// rather than a matter of trust.

pipeline {
  agent any

  environment {
    DOCKERHUB_USER = 'sohanbhadalkar'
    APP_IMAGE      = "${DOCKERHUB_USER}/sample-api"
    GUARD_IMAGE    = "${DOCKERHUB_USER}/api-guard:1"
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
    // Short SHA is the artifact identity: every deploy is traceable to one
    // commit, and a rollback names an exact build rather than "the last one".
    TAG            = "${env.GIT_COMMIT ? env.GIT_COMMIT.take(7) : env.BUILD_NUMBER}"
  }

  options {
    timestamps()
    timeout(time: 30, unit: 'MINUTES')
  }

  stages {

    stage('Checkout') {
      steps {
        checkout scm
        // The gate compares against origin/main. A shallow clone does not have
        // it, and the failure surfaces as a confusing "no spec at origin/main".
        sh 'git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main || true'
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

          sh """
            docker pull ${GUARD_IMAGE}
            docker run --rm --network ${network} \
              --volumes-from ${JENKINS_CONTAINER} -w \$(pwd) ${GUARD_IMAGE} \
              check --config api-guard.yaml \
                    --generated-spec generated.yaml \
                    --url http://api:8000
          """
        }
      }
    }

    // Everything below here only runs because the gate passed.

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

  post {
    always {
      // The ephemeral stack goes; staging stays running on purpose.
      sh "docker compose -f ${TEST_STACK} down -v || true"

      junit allowEmptyResults: true, testResults: 'api-guard-report/junit.xml'
      archiveArtifacts artifacts: 'api-guard-report/**', allowEmptyArchive: true

      // The MCP server reads result.json from these archived artifacts, which
      // is why no separate result storage is needed.
      script {
        if (fileExists('api-guard-report/report.md')) {
          echo readFile('api-guard-report/report.md')
        }
      }
    }
    failure {
      echo 'Contract gate or smoke test failed. Nothing new was deployed.'
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
