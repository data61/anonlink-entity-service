# Production Deployment 

The entity service has been deployed to Kubernetes clusters on GCE and
AWS. The entity service has been designed to scale across multiple nodes
and handle node failure.

## Bring up a Kubernetes cluster:

Out of scope for this documentation, for AWS there is a good
tutorial [here](https://github.com/coreos/kube-aws).

Recommended worker instance type is `r3.4xlarge` - spot instances are 
fine as we handle node failure.


## We assume the cluster has an ingress controller

Deploy the [traefik ingress controller](https://docs.traefik.io/user-guide/kubernetes/) 
into the kube-system namespace with:

    helm install --name traefik --namespace kube-system --values traefik.yaml stable/traefik

Note you can update the traefik.yaml file and upgrade in place with:

    helm upgrade traefik --namespace kube-system --values traefik.yaml stable/traefik


## Deploy the system

Helm can be used to easily deploy the system to a kubernetes cluster.

Pull the deps:
    
    helm dependency update


Install the whole system

    helm install --set domain="es.data61.xyz" . --name="entityservice"


# Manually using kubernetes resources

# Provision cluster resources

`kubectl` uses the same interface to provision all types of resource:

    kubectl create -f some-resource.yaml

Before deploying the entity service we need to provision a few other
things on the cluster. An existing N1 cluster may already have these.

    kubectl create -f aws-storage.yaml -f n1-coreos-secret.yaml


## Dynamically provisioned storage:

When pods require persistent storage this can either be manually provided,
or dynamically.

For a cluster on AWS the `aws-storage.yaml` resource will dynamically
provision elastic block store volumes.

## Docker login credentials

Add secret to enable pulling from private quay.io repository:

`n1-coreos-secret.yaml`


# Deploy the entity service

    cd entityservice
    kubectl create -f db/volume-claim.yaml -f db/db-password-secret.yaml
    kubectl create -f db/postgres-service.yaml -f db/postgres-deployment.yaml
    kubectl create -f redis
    kubectl create -f worker
    kubectl create -f api
    kubectl create -f monitor


## Run an e2e test

    kubectl create -f jobs/e2e-test-job.yaml

## To view the celery monitor:

Find the pod that the monitor is running on then forward the port:

    kubectl port-forward entityservice-monitor-4045544268-s34zl 8888:8888

## To add the Route53 DNS record

Find out the Amazon Load Balancer address:

    kubectl describe service entityservice-api

Add a CNAME record to aws.



# Helm bits and bobs:

Examples:

https://github.com/deis/workflow/tree/master/charts/workflow

Postgres was a bit annoying so I have packaged it up manually. Ideally it would be another line in `requirements.yaml` as opposed
to a whole new sub chart. Here is what it is based off:

    https://github.com/kubernetes/charts/tree/master/stable/postgresql

This would need to be added back to the requirements file:

    - name: postgresql
      repository: https://kubernetes-charts.storage.googleapis.com
      version: 0.3.0
