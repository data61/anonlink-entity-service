void setBuildStatus(String message, String state) {
  step([
    $class: "GitHubCommitStatusSetter",
    statusResultSource: [ $class: "ConditionalStatusResultSource", results: [[$class: "AnyBuildResult", message: message, state: state]] ]
  ]);
}

node {
  stage('Checkout') {
      checkout scm
  }

  //stage('Server Unittests') {
  //  try {
  //    sh '''
  //      cd backend
  //      python3.5 -m venv testenv
  //      testenv/bin/python --version
  //      testenv/bin/python testenv/bin/pip install --upgrade pip
  //      testenv/bin/python testenv/bin/pip install --upgrade -r requirements.txt
  //      testenv/bin/python testenv/bin/pip list --format=columns
  //      testenv/bin/python -m unittest discover -s .
  //      rm -rf testenv
  //    '''
  //    currentBuild.result = 'SUCCESS'
  //    setBuildStatus("Unit tests passed", "SUCCESS");
  //  } catch (Exception err) {
  //    currentBuild.result = 'FAILURE'
  //    setBuildStatus("Tests failed", "FAILURE");
  //  }
  //}

  stage('Docker Build') {
    try {
      sh '''
        docker info
        #docker build -t quay.io/n1analytics/n1-webserver .
      '''

      def app = docker.build "quay.io/n1analytics/entity-app:${env.BUILD_TAG}"
      def frontend = docker.build "quay.io/n1analytics/entity-nginx:{$env.BUILD_TAG}"

      //app.push() // Record this build
      //frontend.push() // Record this build

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