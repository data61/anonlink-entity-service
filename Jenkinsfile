void setBuildStatus(String message, String state) {
  step([
    $class: "GitHubCommitStatusSetter",
    reposSource: [$class: "ManuallyEnteredRepositorySource", url: "https://github.com/n1analytics/entity-service"],
    contextSource: [$class: 'ManuallyEnteredCommitContextSource', context: 'jenkins'],
    statusResultSource: [ $class: "ConditionalStatusResultSource", results: [[$class: "AnyBuildResult", message: message, state: state]] ]
  ]);
}

node('docker&&multicore&&ram') {

  stage ('Checkout') {
    checkout scm
  }

  // Login to quay.io
  withCredentials([usernamePassword(credentialsId: 'quayion1analyticsbuilder', usernameVariable: 'USERNAME_QUAY', passwordVariable: 'PASSWORD_QUAY')]) {
    sh 'docker login -u=${USERNAME_QUAY} -p=${PASSWORD_QUAY} quay.io'
  }


  def errorMsg = "Unknown failure";
  def composeproject = "es-${BRANCH_NAME}-${BUILD_NUMBER}".replaceAll("-", "").replaceAll("_", "").toLowerCase();
  try {

    stage('Docker Build') {

      try {
          sh """
            cd backend
            docker build -t quay.io/n1analytics/entity-app:latest .
            cd ../frontend
            docker build -t quay.io/n1analytics/entity-nginx:latest .
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
        sh """
        # Start all the containers (including tests)
        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p ${composeproject} up -d
        """
        setBuildStatus("Integration test in progress", "PENDING");
      } catch (err) {
        errorMsg = "Failed to start CI integration test with docker compose";
        throw err;
      }
    }

    stage('Integration Tests') {
      try {
        sh """
          sleep 2
          docker logs -t -f ${composeproject}_tests_1
          exit `docker inspect --format='{{.State.ExitCode}}' ${composeproject}_tests_1`
        """
        setBuildStatus("Integration tests complete", "SUCCESS");
      } catch (err) {
        errorMsg = "Integration tests didn't pass";
        throw err;
      }
    }

    stage('Documentation') {
      try {
        sh """
          mkdir -p html
          chmod 777 html

          docker run -v `pwd`:/src -v `pwd`/html:/build quay.io/n1analytics/entity-app:doc-builder

          cd html
          zip -q -r n1-docs.zip *
          mv n1-docs.zip ../
          cd ..
          cp -r html/* frontend/static
          docker build -t quay.io/n1analytics/entity-nginx:latest frontend
        """

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
    try {
        String cmdInspect = "docker inspect --format='{{.State.ExitCode}}' "+ composeproject + "_tests_1"
        sh cmdInspect
    } catch (Exception e) {
        print("Tests failed with exception " + e.toString())
        throw e
    } finally {
        String cmdTearDown = "docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p " + composeproject + " down -v"
        sh cmdTearDown
    }
  }
}

node('helm && kubectl') {

  stage('K8s Deployment') {
    checkout scm

    // Pre-existant configuration file available from jenkins
    CLUSTER_CONFIG_FILE_ID = "awsClusterConfig"

    DEPLOYMENT = composeproject
    NAMESPACE = "default"

    def TAG = sh(script: """python tools/get_docker_tag.py $BRANCH_NAME app""", returnStdout: true).trim()
    def NGINXTAG = sh(script: """python tools/get_docker_tag.py $BRANCH_NAME nginx""", returnStdout: true).trim()


    configFileProvider([configFile(fileId: CLUSTER_CONFIG_FILE_ID, variable: 'KUBECONFIG')]) {
      withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'aws_jenkins', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
        try {
          timeout(time: 30, unit: 'MINUTES') {
            sh """
                cat <<EOF > deployment/entity-service/test-versions.yaml
api:
  www:
    image:
      tag: "${NGINXTAG}"
  app:
    image:
      tag: "${TAG}"
  dbinit:
    image:
      tag: "${TAG}"
workers:
  image:
    tag: "${TAG}"
EOF


                cd deployment/entity-service
                helm dependency update
                helm upgrade --install --wait --namespace ${NAMESPACE} ${DEPLOYMENT} . \
                    -f values.yaml -f test-versions.yaml \
                    --set api.app.debug=true \
                    --set api.app.image.tag=${TAG} \
                    --set workers.image.tag=${TAG} \
                    --set workers.replicaCount=2 \
                    --set minio.mode="standalone" \
                    --set minio.persistence.size="4Gi" \
                    --set api.ingress.enabled=false

                # give the cluster a chance to provision volumes etc, assign an IP to the service, then create a new job to test it
                sleep 300
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
          - "--long"
      imagePullSecrets:
      - name: n1-quay-pull-secret
EOF
                sleep 30
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
            kubectl delete job -lapp=${DEPLOYMENT}-entity-service
            """

            throw error
          }
      }
    }
    setBuildStatus("K8s Deployment Test", "SUCCESS");
  }
}

