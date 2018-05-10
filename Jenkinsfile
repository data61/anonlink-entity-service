void setBuildStatus(String message, String state) {
  step([
    $class: "GitHubCommitStatusSetter",
    reposSource: [$class: "ManuallyEnteredRepositorySource", url: "https://github.com/n1analytics/entity-service"],
    contextSource: [$class: 'ManuallyEnteredCommitContextSource', context: 'jenkins'],
    statusResultSource: [ $class: "ConditionalStatusResultSource", results: [[$class: "AnyBuildResult", message: message, state: state]] ]
  ]);
}

//node('docker') {
//
//  stage ('Checkout') {
//    checkout scm
//  }
//
//  // Login to quay.io
//  withCredentials([usernamePassword(credentialsId: 'quayion1analyticsbuilder', usernameVariable: 'USERNAME_QUAY', passwordVariable: 'PASSWORD_QUAY')]) {
//    sh 'docker login -u=${USERNAME_QUAY} -p=${PASSWORD_QUAY} quay.io'
//  }
//
//  def errorMsg = "Unknown failure";
//
//  try {
//
//    stage('Docker Build') {
//
//      try {
//          sh """
//            cd backend
//            docker build -t quay.io/n1analytics/entity-app .
//            cd ../frontend
//            docker build -t quay.io/n1analytics/entity-nginx .
//            cd ../docs
//            docker build -t quay.io/n1analytics/entity-app:doc-builder .
//          """
//          setBuildStatus("Docker build complete", "PENDING");
//      } catch (err) {
//        errorMsg = "Failed to build docker images";
//        throw err;
//      }
//    }
//
//    stage('Compose Deploy') {
//      try {
//        sh '''
//        # Stop and remove any existing entity service
//        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest down -v
//
//        # Start all the containers (including tests)
//        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p entityservicetest up -d
//        '''
//        setBuildStatus("Integration test in progress", "PENDING");
//      } catch (err) {
//        errorMsg = "Failed to start CI integration test with docker compose";
//        throw err;
//      }
//    }
//
//    stage('Integration Tests') {
//      try {
//        sh '''
//          sleep 2
//          docker logs -t -f entityservicetest_tests_1
//          exit `docker inspect --format='{{.State.ExitCode}}' entityservicetest_tests_1`
//        '''
//        setBuildStatus("Integration tests complete", "SUCCESS");
//      } catch (err) {
//        errorMsg = "Integration tests didn't pass";
//        throw err;
//      }
//    }
//
//    stage('Documentation') {
//      try {
//        sh '''
//          mkdir -p html
//          chmod 777 html
//
//          docker run -v `pwd`/docs:/src -v `pwd`/html:/build quay.io/n1analytics/entity-app:doc-builder
//
//          cd html
//          zip -q -r n1-docs.zip *
//          mv n1-docs.zip ../
//        '''
//
//        archiveArtifacts artifacts: 'n1-docs.zip', fingerprint: true
//        setBuildStatus("Documentation Built", "SUCCESS");
//
//      } catch (err) {
//        errorMsg = "Couldn't build docs";
//        throw err;
//      }
//    }
//
//    stage('Publish') {
//      // Login to quay.io
//      withCredentials([usernamePassword(credentialsId: 'quayion1analyticsbuilder', usernameVariable: 'USERNAME_QUAY', passwordVariable: 'PASSWORD_QUAY')]) {
//        sh 'docker login -u=${USERNAME_QUAY} -p=${PASSWORD_QUAY} quay.io'
//
//        try {
//            sh '''
//              ./tools/upload.sh
//            '''
//            setBuildStatus("Published Docker Images", "SUCCESS");
//        } catch (Exception err) {
//          errorMsg = "Publishing docker images to quay.io failed";
//          throw err
//        }
//
//        sh 'docker logout quay.io'
//      }
//    }
//
//  } catch (err) {
//    currentBuild.result = 'FAILURE'
//    setBuildStatus(errorMsg,  "FAILURE");
//  } finally {
//    sh './tools/ci_cleanup.sh'
//  }
//
//}

node('helm && kubectl') {

  stage('K8s Deployment') {
    checkout scm

    // Pre-existant configuration file available from jenkins
    CLUSTER_CONFIG_FILE_ID = "awsClusterConfig"

    DEPLOYMENT = "es-${BRANCH_NAME}-${BUILD_NUMBER}"
    NAMESPACE = "default"
    TAG = "v1.8.0-develop"

    configFileProvider([configFile(fileId: CLUSTER_CONFIG_FILE_ID, variable: 'KUBECONFIG')]) {
      withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'aws_jenkins', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
        try {
          timeout(time: 15, unit: 'MINUTES') {
            sh """
                cd deployment/entity-service
                helm dependency update
                helm upgrade --install --namespace ${NAMESPACE} ${DEPLOYMENT} . \
                    -f values.yaml -f minimal-values.yaml -f versions.yaml \
                    --set api.ingress.enabled=false

                # give the cluster a chance to assign an IP to the service, then create a new job to test it
                sleep 90
                """

            def serviceIP = sh(script: """
                kubectl get services -lapp=${DEPLOYMENT}-entity-service -o jsonpath="{.items[0].spec.clusterIP}"
            """, returnStdout: true)

            sh """
                cat <<EOF | kubectl create -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: ${DEPLOYMENT}-test
  labels:
    jobgroup: jenkins-es-integration-test
    deployment: ${DEPLOYMENT}
spec:
  completions: 1
  parallelism: 1
  template:
    metadata:
      labels:
        jobgroup: jenkins-es-integration-test
        deployment: ${DEPLOYMENT}
    spec:
      restartPolicy: Never
      containers:
      - name: entitytester
        image: quay.io/n1analytics/entity-app:${TAG}
        imagePullPolicy: Always
        env:
          - name: ENTITY_SERVICE_URL
            value: http://$serviceIP/api/v1
        command:
          - "python"
          - "-m"
          - "pytest"
          - "entityservice/tests"
          - "-v"
      imagePullSecrets:
      - name: n1-quay-pull-secret
EOF
                sleep 10
            """

                def jobPodName = sh(script: """
                    kubectl get pods -l deployment=${DEPLOYMENT} -o jsonpath="{.items[0].metadata.name}"
                """, returnStdout: true)
                println jobPodName

            sh """
                # Watch the output
                kubectl logs -f $jobPodName


                # Clean up
                kubectl delete job ${DEPLOYMENT}-test
                helm delete --purge ${DEPLOYMENT}
            """

            }
          } catch(error) { // timeout reached or input false
            sh """
            helm delete --purge ${DEPLOYMENT}
            # kubectl delete job ${DEPLOYMENT}-test
            """

            throw error
          }
      }
    }
  }
}

