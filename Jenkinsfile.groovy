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
String gitContextLocalBenchmark = "jenkins-benchmark"
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

    composeProject = "es-${BRANCH_NAME}-${BUILD_NUMBER}".replaceAll("[-_.]", "").toLowerCase()
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
          String imageNameLabel = "quay.io/n1analytics/entity-docs:latest"
          dockerUtils.dockerCommand("build -t " + imageNameLabel + " .")
        }
        dir("benchmarking") {
          String imageNameLabel = "quay.io/n1analytics/entity-benchmark:latest"
          dockerUtils.dockerCommand("build -t " + imageNameLabel + " .")
        }
        gitCommit.setSuccessStatus(gitContextDockerBuild)
      } catch (err) {
        print("Error in docker build stage:\n" + err)
        gitCommit.setFailStatus(gitContextDockerBuild)
        throw err
      }
    }

    stage('Compose Deploy') {
      gitCommit.setInProgressStatus(gitContextComposeDeploy);
      try {
        echo("Start all the containers (including tests)")
        sh """
        docker-compose -v
        docker-compose \
            -f tools/docker-compose.yml \
            -f tools/ci.yml \
            -p ${composeProject} up -d \
            db minio redis backend db_init worker nginx tests
        """

        gitCommit.setSuccessStatus(gitContextComposeDeploy)
      } catch (err) {
        print("Error in compose deploy stage:\n" + err)
        gitCommit.setFailStatus(gitContextComposeDeploy)
        throw err
      }
    }

    stage('Integration Tests') {
      gitCommit.setInProgressStatus(gitContextIntegrationTests);
      try {
        DockerContainer containerTests = new DockerContainer(dockerUtils, composeProject + "_tests_1")
        sleep 2
        timeout(time: 60, unit: 'MINUTES') {
          containerTests.watchLogs()

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
        throw err
      }
    }

    stage('Benchmark') {
      gitCommit.setInProgressStatus(gitContextLocalBenchmark);
      String benchmarkContainerName = composeProject + "benchmark"
      String networkName = composeProject + "_default"
      String localserver = "http://nginx:8851"

      try {
        timeout(time: 15, unit: 'MINUTES') {
          def experiments = readJSON text: """
          [
            {
              "sizes": ["100K", "100K"],
              "threshold": 0.95
            }
          ]
          """

          // Create a docker volume to use as a cache (if it doesn't exist)
          sh '''
          ./tools/create-benchmark-cache.sh
          '''

          // We use a custom experiments for jenkins
          writeJSON file: 'linkage-bench-cache-experiments.json', json: experiments

          sh """
          echo "Copying experiments into cache volume"
          docker run --rm -v `pwd`:/src \
                -v linkage-benchmark-data:/data busybox \
                sh -c "cp -r /src/linkage-bench-cache-experiments.json /data; chown -R 1000:1000 /data"
          echo "Starting benchmarks"
          docker run \
                --name ${benchmarkContainerName} \
                --network ${networkName} \
                -e SERVER=${localserver} \
                -e DATA_PATH=/cache \
                -e EXPERIMENT=/cache/linkage-bench-cache-experiments.json \
                -e RESULTS_PATH=/app/results.json \
                --mount source=linkage-benchmark-data,target=/cache \
                quay.io/n1analytics/entity-benchmark:latest

          docker cp ${benchmarkContainerName}:/app/results.json results.json
          """

          archiveArtifacts artifacts: "results.json", fingerprint: true
          gitCommit.setSuccessStatus(gitContextLocalBenchmark)
        }
      } catch (err) {
        print("Error or timeout in benchmarking stage:\n" + err)
        gitCommit.setFailStatus(gitContextLocalBenchmark)

        throw err
      } finally {
          sh """
            docker rm -v ${benchmarkContainerName}
          """
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
        throw err
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
                    -f values.yaml -f minimal-values.yaml -f test-versions.yaml \
                    --set api.app.debug=true \
                    --set api.ingress.enabled=false \
                    --set api.certManager.enabled=false \
                    --set provision.redis=true
                """
              // give the cluster a chance to provision volumes etc, assign an IP to the service, then create a new job to test it
              sleep(time: 120, unit: "SECONDS")
            }

            String serviceIP = sh(script: """
                kubectl get services -lapp=${DEPLOYMENT}-entity-service -o jsonpath="{.items[0].spec.clusterIP}"
            """, returnStdout: true).trim()

            pvc = createK8sTestJob(DEPLOYMENT, QuayIORepo.ENTITY_SERVICE_APP.getRepo() + ":" + TAG, serviceIP)

            sleep(time: 60, unit: "SECONDS")

            def jobPodName = sh(script: """
                kubectl get pods -l deployment=${DEPLOYMENT} -o jsonpath="{.items[0].metadata.name}"
            """, returnStdout: true).trim()
            echo jobPodName

            sh """
                # Watch the output
                kubectl logs -f $jobPodName
            """

            resultFile = getResultsFromK8s(DEPLOYMENT, pvc)

            junit resultFile

          }
          gitCommit.setSuccessStatus(gitContextKubernetesDeployment)
        } catch (error) { // timeout reached or input false
          print("Error in k8s deployment stage:\n" + error)
          gitCommit.setFailStatus(gitContextKubernetesDeployment)
          throw new Exception("The k8s integration tests failed.")
        } finally {
          try {
            sh """
            helm delete --purge ${DEPLOYMENT}
            kubectl delete job -lapp=${DEPLOYMENT}-entity-service
            kubectl delete job ${DEPLOYMENT}-test
            kubectl delete all -ldeployment=${DEPLOYMENT}
            kubectl delete all -lrelease=${DEPLOYMENT}
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


void createK8sFromManifest(LinkedHashMap<String, Object> manifest) {
  String fileName = "tmp.yaml"
  if (fileExists(fileName)) {
    sh "rm " + fileName
  }
  writeYaml(file: fileName, data: manifest)
  String shCommand = "kubectl create -f " + fileName
  sh shCommand
  sh "rm " + fileName
}

String getResultsFromK8s(String deploymentName, String pvcName) {
    String pod_name = "${BRANCH_NAME}-${BUILD_NUMBER}-tmppod"

    def k8s_pod_manifest = [
          "apiVersion": "v1",
          "kind": "Pod",
          "metadata": [
                  "name": pod_name,
                  "labels"    : [
                          "deployment": deploymentName
                  ]
          ],
          "spec": [
                  "restartPolicy"   : "Never",
                  "volumes": [
                          [
                                  "name": "results",
                                  "persistentVolumeClaim": [
                                          "claimName": pvcName
                                  ]
                          ]

                  ],

                  "containers"      : [
                          [
                                  "name"           : "resultpod",
                                  "image"          : "python",
                                  "command"        : [
                                          "sleep",
                                          "3600"
                                  ],
                                  "volumeMounts": [[
                                                           "mountPath": "/mnt",
                                                           "name": "results"
                                                   ]]
                          ]
                  ],
          ]
  ]

  createK8sFromManifest(k8s_pod_manifest)
  sleep(time: 60, unit: "SECONDS")
  String out = "k8s-results.xml"
  sh """
      # fetch the results from the running pod
      kubectl cp $NAMESPACE/$pod_name:/mnt/results.xml $out

      # delete the temp pod
      kubectl delete pod $pod_name

      # delete the pvc
      kubectl delete pvc -l deployment=$deploymentName
  """
  return out
}

String createK8sTestJob(String deploymentName, String imageNameWithTag, String serviceIP) {
  String pvc_name =  deploymentName + "-test-results"

  def k8s_pvc_manifest = [
      "apiVersion": "v1",
      "kind"      : "PersistentVolumeClaim",
      "metadata"  : [
          "name": pvc_name,
          "labels"    : [
              "jobgroup": "jenkins-es-integration-test",
              "deployment": deploymentName
          ]
      ],
      "spec"      : [
          "storageClassName": "default",
          "accessModes": [
                  "ReadWriteOnce"
          ],
          "resources"   : [
              "requests": [
                  "storage": "1Gi"
              ]
           ]

       ]
  ]


  def k8s_job_manifest = [
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
                                  "securityContext": [
                                          "runAsUser": 0,
                                          "fsGroup": 0
                                  ],
                                  "restartPolicy"   : "Never",
                                  "volumes": [
                                          [
                                                  "name": "results",
                                                  "persistentVolumeClaim": [
                                                          "claimName": pvc_name
                                                  ]
                                          ]

                                  ],

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
                                                          "entityservice/tests",
                                                          "--junit-xml=/mnt/results.xml"
                                                  ],
                                                  "volumeMounts": [[
                                                          "mountPath": "/mnt",
                                                          "name": "results"
                                                  ]]
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

  createK8sFromManifest(k8s_pvc_manifest)
  createK8sFromManifest(k8s_job_manifest)

  return pvc_name
}
