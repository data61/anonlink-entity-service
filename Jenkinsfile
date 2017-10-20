void setBuildStatus(String message, String state) {
  step([
    $class: "GitHubCommitStatusSetter",
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


  stage('Docker Build') {
    try {
      sh """
        cd backend
        docker build -t quay.io/n1analytics/entity-app:${env.BUILD_TAG} .
        cd ../frontend
        docker build -t quay.io/n1analytics/entity-nginx:${env.BUILD_TAG} .
      """

      currentBuild.result = 'SUCCESS'
      setBuildStatus("Docker build complete", "SUCCESS");
    } catch (Exception err) {
      currentBuild.result = 'FAILURE'
      setBuildStatus("Docker build failed", "FAILURE");
    }
  }

  stage('Compose Deploy') {
    try {
        sh '''
          docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p n1webtest up -d
        '''
        currentBuild.result = 'SUCCESS'
        setBuildStatus("Build complete", "SUCCESS");
    } catch (Exception err) {
        currentBuild.result = 'FAILURE'
        setBuildStatus("Tests failed", "FAILURE");
    }
  }

  stage('Integration Tests') {
    try {
        sh '''
          docker logs -t -f entityservicetest_ci_1
          exit `docker inspect --format='{{.State.ExitCode}}' entityservicetest_ci_1`
        '''
        currentBuild.result = 'SUCCESS'
        setBuildStatus("Integration tests complete", "SUCCESS");
    } catch (Exception err) {
        currentBuild.result = 'FAILURE'
        setBuildStatus("Tests failed", "FAILURE");
    }
  }

}