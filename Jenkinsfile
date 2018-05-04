void setBuildStatus(String message, String state) {
  step([
    $class: "GitHubCommitStatusSetter",
    reposSource: [$class: "ManuallyEnteredRepositorySource", url: "https://github.com/n1analytics/entity-service"],
    contextSource: [$class: 'ManuallyEnteredCommitContextSource', context: 'jenkins'],
    statusResultSource: [ $class: "ConditionalStatusResultSource", results: [[$class: "AnyBuildResult", message: message, state: state]] ]
  ]);
}

node('docker') {

  stage ('Checkout') {
    checkout scm
  }

  // Login to quay.io
  withCredentials([usernamePassword(credentialsId: 'quayion1analyticsbuilder', usernameVariable: 'USERNAME_QUAY', passwordVariable: 'PASSWORD_QUAY')]) {
    sh 'docker login -u=${USERNAME_QUAY} -p=${PASSWORD_QUAY} quay.io'
  }

  def errorMsg = "Unknown failure";

  try {

    stage('Docker Build') {

      try {
          sh """
            cd backend
            docker build -t quay.io/n1analytics/entity-app .
            cd ../frontend
            docker build -t quay.io/n1analytics/entity-nginx .
            cd ../docs
            docker build -t quay.io/n1analytics/entity-app:doc-builder .
          """
          setBuildStatus("Docker build complete", "PENDING");
      } catch (err) {
        errorMsg = "Failed to build docker images";
        throw err;
      }
    }

    stage('Compose Deploy') {
      try {
        sh '''
        # Stop and remove any existing entity service
        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest down -v

        # Start all the containers (including tests)
        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d
        '''
        setBuildStatus("Integration test in progress", "PENDING");
      } catch (err) {
        errorMsg = "Failed to start CI integration test with docker compose";
        throw err;
      }
    }

    stage('Integration Tests') {
      try {
        sh '''
          sleep 2
          docker logs -t -f entityservicetest_tests_1
          exit `docker inspect --format='{{.State.ExitCode}}' entityservicetest_tests_1`
        '''
        setBuildStatus("Integration tests complete", "SUCCESS");
      } catch (err) {
        errorMsg = "Integration tests didn't pass";
        throw err;
      }
    }

    stage('Documentation') {
      try {
        sh '''
          mkdir -p html
          chmod 777 html

          docker run -v `pwd`/docs:/src -v `pwd`/html:/build quay.io/n1analytics/entity-app:doc-builder

          cd html
          zip -q -r n1-docs.zip *
          mv n1-docs.zip ../
        '''

        archiveArtifacts artifacts: 'n1-docs.zip', fingerprint: true
        setBuildStatus("Documentation Built", "SUCCESS");

      } catch (err) {
        errorMsg = "Couldn't build docs";
        throw err;
      }
    }

    stage('Publish') {
      // Login to quay.io
      withCredentials([usernamePassword(credentialsId: 'quayion1analyticsbuilder', usernameVariable: 'USERNAME_QUAY', passwordVariable: 'PASSWORD_QUAY')]) {
        sh 'docker login -u=${USERNAME_QUAY} -p=${PASSWORD_QUAY} quay.io'

        try {
            sh '''
              ./tools/upload.sh
            '''
            setBuildStatus("Published Docker Images", "SUCCESS");
        } catch (Exception err) {
          errorMsg = "Publishing docker images to quay.io failed";
          throw err
        }

        sh 'docker logout quay.io'
      }
    }

  } catch (err) {
    currentBuild.result = 'FAILURE'
    setBuildStatus(errorMsg,  "FAILURE");
  } finally {
    sh './tools/ci_cleanup.sh'
  }

}

node('helm && kubectl') {

  stage('K8s Deployment') {
    // Pre-existant configuration file available from jenkins
    CLUSTER_CONFIG_FILE_ID = "awsClusterConfig"

    DEPLOYMENT = "es-${BRANCH_NAME}-${BUILD_NUMBER}"
    NAMESPACE = "default"

    configFileProvider([configFile(fileId: CLUSTER_CONFIG_FILE_ID, variable: 'KUBECONFIG')]) {

        try {
          timeout(time: 10, unit: 'MINUTES') {
            withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'aws_jenkins', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
              sh """
                cd deployment/entity-service
                helm upgrade --install --namespace ${NAMESPACE} ${DEPLOYMENT} . \
                    -f values.yaml -f minimal-values.yaml \
                    --set api.ingress.enabled=false
                    --dry-run
              """

            }
          }
        } catch(error) { // timeout reached or input false

          sendSlackMsg(
            'danger',
            "Entity service deployment failed.")

          throw error
        }
      }
    }
}

