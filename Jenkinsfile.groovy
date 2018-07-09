@Library("N1Pipeline@feature-entity-service")
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
          while (containerTests.isRunning()) {
            sleep 10
          }
          if (containerTests.getExitCode() != "0") {
            throw new Exception("The tests failed.")
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
      // TODO Update this stage with the library.
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
          Map<String, String> dicTestVersions = [
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

          Map<String, String> dicKubernetesTestVariables = [
              "apiVersion": "batch/v1",
              "kind"      : "Job",
              "metadata"  : [
                  "name": DEPLOYMENT + "-test"
              ],
              "labels"    : [
                  "jobgroup": "jenkins-es-integration-test"
              ],
              "deployment": DEPLOYMENT,
              "spec"      : [
                  "completions": 1,
                  "parallelism": 1,
                  "template"   : [
                      "metadata": [
                          "labels": [
                              "jobgroup"  : "jenkins-es-integration-test",
                              "deployment": DEPLOYMENT
                          ]
                      ],
                      "spec"    : [
                          "restartPolicy"   : "Never",
                          "containers"      : [
                              [
                                  "name"           : "entitytester",
                                  "image"          : QuayIORepo.ENTITY_SERVICE_APP + ":" + TAG,
                                  "imagePullPolicy": "Always",
                                  "env"            : [
                                      [
                                          "name" : ENTITY_SERVICE_URL,
                                          "value": "http://" + serviceIP + "/api/v1"
                                      ]
                                  ],
                                  "command"        : [
                                      "python",
                                      "-m",
                                      "pytest",
                                      "entityservice/tests",
                                      "--long"
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

          timeout(time: 30, unit: 'MINUTES') {
            dir("deployment/entity-service") {
              writeYaml(file: "test-versions.yaml", data: dicTestVersions)
              sh """
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
                """
              // give the cluster a chance to provision volumes etc, assign an IP to the service, then create a new job to test it
              sleep(time: 300, unit: "SECONDS")
            }

            String serviceIP = sh(script: """
                kubectl get services -lapp=${DEPLOYMENT}-entity-service -o jsonpath="{.items[0].spec.clusterIP}"
            """, returnStdout: true).trim()

            writeYaml(file: "test-variables.yaml", data: dicKubernetesTestVariables)
            sh """
                kubectl create -f test-variables.yaml
            """
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
          sh """
            helm delete --purge ${DEPLOYMENT}
            kubectl delete job -lapp=${DEPLOYMENT}-entity-service
            kubectl delete job ${DEPLOYMENT}-test
            """

        }
      }
    }
  }
}
