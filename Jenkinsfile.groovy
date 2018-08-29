@Library("N1Pipeline@0.0.19")
import com.n1analytics.docker.DockerContainer;
import com.n1analytics.docker.DockerUtils;
import com.n1analytics.docker.QuayIORepo
import com.n1analytics.git.GitUtils;
import com.n1analytics.git.GitCommit;
import com.n1analytics.git.GitRepo;

String gitContextDockerBuild = "required-docker-images-build"
String gitContextComposeDeploy = "required-dockercompose-deploy"
String gitContextIntegrationTests = "required-integration-tests"
String gitContextDocumentation = "required-build-documentation"
String gitContextPublish = "required-publish-docker-images"
String gitContextKubernetesDeployment = "optional-kubernetes-deployment"
DockerUtils dockerUtils
GitCommit gitCommit
String composeProject

node('docker&&multicore&&ram') {

  stage ('Initialisation') {
    // Knowing this git commit will enable us to send to github the corresponding status.
    gitCommit = GitUtils.checkoutFromSCM(this)
    // Login to quay.io
    dockerUtils = new DockerUtils(this)
    dockerUtils.dockerLoginQuayIO(QuayIORepo.ENTITY_SERVICE_APP)

    composeProject = "es-${BRANCH_NAME}-${BUILD_NUMBER}".replaceAll("-", "").replaceAll("_", "").toLowerCase();
  }

  try {

    stage('Docker Build') {
      gitCommit.setInProgressStatus(gitContextDockerBuild);
      try {
        dir("backend") {
          String imageNameLabel = QuayIORepo.ENTITY_SERVICE_APP.getRepo() + ":latest"
          dockerUtils.dockerCommand("build -t " + imageNameLabel + " .")
        }
        dir("frontend") {
          String imageNameLabel = QuayIORepo.ENTITY_SERVICE_NGINX.getRepo() + ":latest"
          dockerUtils.dockerCommand("build -t " + imageNameLabel + " .")
        }
        dir("docs") {
          String imageNameLabel = QuayIORepo.ENTITY_SERVICE_APP.getRepo() + ":doc-builder"
          dockerUtils.dockerCommand("build -t " + imageNameLabel + " .")
        }
        gitCommit.setSuccessStatus(gitContextDockerBuild)
      } catch (err) {
        print("Error in docker build stage:\n" + err)
        gitCommit.setFailStatus(gitContextDockerBuild)
        throw err;
      }
    }

    stage('Compose Deploy') {
      gitCommit.setInProgressStatus(gitContextComposeDeploy);
      try {
        echo("Start all the containers (including tests)")
        sh """
        docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p ${composeProject} up -d
        """
        gitCommit.setSuccessStatus(gitContextComposeDeploy)
      } catch (err) {
        print("Error in compose deploy stage:\n" + err)
        gitCommit.setFailStatus(gitContextComposeDeploy)
        throw err;
      }
    }

    stage('Integration Tests') {
      gitCommit.setInProgressStatus(gitContextIntegrationTests);
      try {
        DockerContainer containerTests = new DockerContainer(dockerUtils, composeProject + "_tests_1")
        sleep 2
        timeout(time: 30, unit: 'MINUTES') {
          containerTests.watchLogs();

          sh("docker logs " + composeProject + "_nginx_1" + " &> nginx.log")
          sh("docker logs " + composeProject + "_backend_1" + " &> backend.log")
          sh("docker logs " + composeProject + "_worker_1" + " &> worker.log")
          sh("docker logs " + composeProject + "_db_1" + " &> db.log")

          archiveArtifacts artifacts: "*.log", fingerprint: false
          if (containerTests.getExitCode() != "0") {
            throw new Exception("The integration tests failed.")
          }
          gitCommit.setSuccessStatus(gitContextIntegrationTests)
        }
      } catch (err) {
        print("Error in integration tests stage:\n" + err)
        gitCommit.setFailStatus(gitContextIntegrationTests)
        throw err;
      }
    }

    stage('Documentation') {
      gitCommit.setInProgressStatus(gitContextDocumentation);
      String dockerContainerDocsBuilderName = composeProject + "docbuilder"
      // TODO Update this stage with the library.
      try {
        sh """
          mkdir -p html
          docker run -v `pwd`:/src --name ${dockerContainerDocsBuilderName} quay.io/n1analytics/entity-app:doc-builder
          docker cp ${dockerContainerDocsBuilderName}:/build `pwd`/html
          cd html/build
          zip -q -r n1-docs.zip *
          mv n1-docs.zip ../../
          cd ../..
          cp -r html/build/* frontend/static
          rm -r html
          docker build -t quay.io/n1analytics/entity-nginx:latest frontend
          docker rm ${dockerContainerDocsBuilderName}
        """

        archiveArtifacts artifacts: 'n1-docs.zip', fingerprint: true
        gitCommit.setSuccessStatus(gitContextDocumentation)
      } catch (err) {
        print("Error in documentation stage:\n" + err)
        gitCommit.setFailStatus(gitContextDocumentation)
        throw err;
      }
    }

    stage('Publish') {
      gitCommit.setInProgressStatus(gitContextPublish);
      try {
          sh '''
            ./tools/upload.sh
          '''
        gitCommit.setSuccessStatus(gitContextPublish)
      } catch (Exception err) {
        print("Error in publish stage:\n" + err)
        gitCommit.setFailStatus(gitContextPublish)
        throw err
      }

      sh 'docker logout quay.io'
    }

  } finally {
    stage("Cleaning") {
      try {
        dockerUtils.dockerLogoutQuayIOWithoutFail()
        String cmdTearDown = "docker-compose -f tools/docker-compose.yml -f tools/ci.yml -p " + composeProject + " down -v"
        sh cmdTearDown
      } catch(Exception err) {
        print("Error in cleaning stage, but do nothing about it:\n" + err)
        // Do nothing on purpose.
      }
    }
  }
}

node('helm && kubectl') {

  stage('K8s Deployment') {
    gitCommit.setInProgressStatus(gitContextKubernetesDeployment)
    GitUtils.checkoutFromSCM(this)

    // Pre-existant configuration file available from jenkins
    CLUSTER_CONFIG_FILE_ID = "awsClusterConfig"

    DEPLOYMENT = composeProject
    NAMESPACE = "default"

    def TAG = sh(script: """python tools/get_docker_tag.py $BRANCH_NAME app""", returnStdout: true).trim()
    def NGINXTAG = sh(script: """python tools/get_docker_tag.py $BRANCH_NAME nginx""", returnStdout: true).trim()


    configFileProvider([configFile(fileId: CLUSTER_CONFIG_FILE_ID, variable: 'KUBECONFIG')]) {
      withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: 'aws_jenkins', secretKeyVariable: 'AWS_SECRET_ACCESS_KEY']]) {
        try {
          dicTestVersions = [
              "api"    : [
                  "www"   : [
                      "image": [
                          "tag": NGINXTAG
                      ]
                  ],
                  "app"   : [
                      "image": [
                          "tag": TAG
                      ]
                  ],
                  "dbinit": [
                      "image": [
                          "tag": TAG
                      ]
                  ]
              ],
              "workers": [
                  "image": [
                      "tag": TAG
                  ]
              ]
          ]

          timeout(time: 30, unit: 'MINUTES') {
            dir("deployment/entity-service") {
              if (fileExists("test-versions.yaml")) {
                sh "rm test-versions.yaml"
              }
              writeYaml(file: "test-versions.yaml", data: dicTestVersions)
              sh """
                helm version
                helm dependency update
                helm upgrade --install --wait --namespace ${NAMESPACE} ${DEPLOYMENT} . \
                    -f values.yaml -f test-versions.yaml \
                    --set api.app.debug=true \
                    --set api.app.image.tag=${TAG} \
                    --set workers.image.tag=${TAG} \
                    --set workers.replicaCount=2 \
                    --set minio.mode="standalone" \
                    --set minio.persistence.size="4Gi" \
                    --set api.ingress.enabled=false \
                    --set api.certManager.enabled=false
                """
              // give the cluster a chance to provision volumes etc, assign an IP to the service, then create a new job to test it
              sleep(time: 300, unit: "SECONDS")
            }

            String serviceIP = sh(script: """
                kubectl get services -lapp=${DEPLOYMENT}-entity-service -o jsonpath="{.items[0].spec.clusterIP}"
            """, returnStdout: true).trim()

            dicKubernetesYamlFile = writeDicKubernetesVariables(DEPLOYMENT, QuayIORepo.ENTITY_SERVICE_APP.getRepo() + ":" + TAG, serviceIP)
            String shCommand = "kubectl create -f " + dicKubernetesYamlFile
            sh shCommand
            sleep(time: 300, unit: "SECONDS")

            def jobPodName = sh(script: """
                kubectl get pods -l deployment=${DEPLOYMENT} -o jsonpath="{.items[0].metadata.name}"
            """, returnStdout: true).trim()
            echo jobPodName

            sh """
                # Watch the output
                kubectl logs -f $jobPodName

                # Clean up
                kubectl delete job ${DEPLOYMENT}-test
                helm delete --purge ${DEPLOYMENT}
            """
          }
          gitCommit.setSuccessStatus(gitContextKubernetesDeployment)
        } catch (error) { // timeout reached or input false
          print("Error in k8s deployment stage:\n" + error)
          gitCommit.setFailStatus(gitContextKubernetesDeployment)
          throw error
        } finally {
          try {
            sh """
            helm delete --purge ${DEPLOYMENT}
            kubectl delete job -lapp=${DEPLOYMENT}-entity-service
            kubectl delete job ${DEPLOYMENT}-test
            """
          } catch(Exception err) {
            print("Error in final cleanup, Ignoring:\n" + err)
            // Do nothing on purpose.
          }
        }
      }
    }
  }
}


String writeDicKubernetesVariables(String deploymentName, String imageNameWithTag, String serviceIP) {
  String yamlFileName = "test-variables.yaml"
  if (fileExists(yamlFileName)) {
    sh "rm " + yamlFileName
  }
  def dicKubernetes = [
      "apiVersion": "batch/v1",
      "kind"      : "Job",
      "metadata"  : [
          "name": deploymentName + "-test",
          "labels"    : [
              "jobgroup": "jenkins-es-integration-test",
              "deployment": deploymentName
          ]
      ],
      "spec"      : [
          "completions": 1,
          "parallelism": 1,
          "template"   : [
              "metadata": [
                  "labels": [
                      "jobgroup"  : "jenkins-es-integration-test",
                      "deployment": deploymentName
                  ]
              ],
              "spec"    : [
                  "restartPolicy"   : "Never",
                  "containers"      : [
                      [
                          "name"           : "entitytester",
                          "image"          : imageNameWithTag,
                          "imagePullPolicy": "Always",
                          "env"            : [
                              [
                                  "name" : "ENTITY_SERVICE_URL",
                                  "value": "http://" + serviceIP + "/api/v1"
                              ]
                          ],
                          "command"        : [
                              "python",
                              "-m",
                              "pytest",
                              "entityservice/tests"
                          ]
                      ]
                  ],
                  "imagePullSecrets": [
                      [
                          "name": "n1-quay-pull-secret"
                      ]
                  ]
              ]

          ]
      ]
  ]
  writeYaml(file: yamlFileName, data: dicKubernetes)
  return yamlFileName
}
