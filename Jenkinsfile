void setBuildStatus(String message, String state) {
  step([
    $class: "GitHubCommitStatusSetter",
    reposSource: [$class: "ManuallyEnteredRepositorySource", url: "https://github.com/n1analytics/entity-service"],
    contextSource: [$class: 'ManuallyEnteredCommitContextSource', context: 'jenkins'],
    statusResultSource: [ $class: "ConditionalStatusResultSource", results: [[$class: "AnyBuildResult", message: message, state: state]] ]
  ]);
}

node('docker') {
  stage('Checkout') {
      checkout scm
  }

  // Login to quay.io
  withCredentials([usernamePassword(credentialsId: 'quayion1analyticsbuilder', usernameVariable: 'USERNAME_QUAY', passwordVariable: 'PASSWORD_QUAY')]) {
    sh 'docker login -u=${USERNAME_QUAY} -p=${PASSWORD_QUAY} quay.io'
  }
  try {

    stage('Docker Build') {

      sh """
        cd backend
        docker build -t quay.io/n1analytics/entity-app .
        cd ../frontend
        docker build -t quay.io/n1analytics/entity-nginx .
      """

      currentBuild.result = 'SUCCESS'
      setBuildStatus("Docker build complete", "PENDING");

    }

    stage('Compose Deploy') {

        sh '''
        # Stop and remove any existing entity service
        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest down -v

        # Start all the containers (including tests)
        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d
        '''

        currentBuild.result = 'SUCCESS'
        setBuildStatus("Integration test in progress", "PENDING");
      }

      stage('Integration Tests') {

        sh '''
          sleep 2
          docker logs -t -f entityservicetest_ci_1
          exit `docker inspect --format='{{.State.ExitCode}}' entityservicetest_ci_1`
        '''
        currentBuild.result = 'SUCCESS'
        setBuildStatus("Integration tests complete", "SUCCESS");

      }

  } catch (Exception err) {
        currentBuild.result = 'FAILURE'
        setBuildStatus("Integration tests failed", "FAILURE");
  } finally {
    sh './tools/ci_cleanup.sh'
  }

}