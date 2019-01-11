# Production Deployment 

The entity service has been deployed to Kubernetes clusters on GCE and
AWS. The entity service has been designed to scale across multiple nodes
and handle node failure.

## Bring up a Kubernetes cluster:

Out of scope for this documentation, for AWS there is a good
tutorial [here](https://github.com/coreos/kube-aws).

Recommended AWS worker instance type is `r3.4xlarge` - spot instances are 
fine as we handle node failure.

## Provision cluster resources

Before deploying the entity service we need to provision a few other
things on the cluster. An existing N1 cluster may already have these.

### Dynamically provisioned storage:

When pods require persistent storage this can either be manually provided,
or dynamically.

For a cluster on AWS we want to use a `StorageClass` that will dynamically 
provision elastic block store volumes. The default `values.yaml` assumes
the existence of a `"gp2"` `storageClass` - change this to suit your cluster. 

Note a default storageclass is usually already part of the cluster:

    kubectl get storageclass

If this is an empty list; on AWS try this:

    kubectl create -f aws-storage.yaml


### Ingress Controller

We assume the cluster has an ingress controller, if this isn't the case 
we will have to add one. The chart has been tested with nginx and treafik.


# Deploy the entity service


## Deploy the system

Helm can be used to easily deploy the system to a kubernetes cluster.

Add the helm repository:

    helm repo add n1charts https://n1analytics.github.io/charts
    helm repo update

Install the `entity-service`:

    helm install n1charts/entity-service
    

## Configuring the deployment

Open the `values.yaml` file in a text editor and adjust to suit your cluster's 
configuration. A better approach is to create a new `your-es-site.yaml` file to
override the values. For example to use the specific version docker images and 
set the hostname to my-site.es.data61.xyz:

```
api:
  ingress:
    hosts:
      - my-site.es.data61.xyz

  www:
    image:
      tag: "v1.3.2-develop"

  app:
    image:
      tag: "v1.7.2-develop"

workers:
  image:
    tag: "v1.7.2-develop"
```

All settings in `values.yaml` can be overridden but take particular note of the 
domain and tls settings for configuring an ingress for a particular cluster.

Also note there is a `minimal-values.yaml` configuration which is a tested deployment
that requires a very small memory and cpu overhead - but of course will only work for
very small testing jobs.

### Private Docker Repository

If you are deploying from a private docker repository remember to push the image
pull secret to the appropriate namespace:
    
    $ kubectl create namespace my-es-site
    $ kubectl create -f n1-coreos-secret.yaml --namespace my-es-site

Note you can have multiple deployments in the same namespace.


### Installation

Assuming you want a minimal resource deployment with custom values from `your-es-site.yaml`
configuration:

    $ helm install --name="your-es-site" entity-service \
        --values values.yaml
        --values minimal-values.yaml \
        --values your-es-site.yaml


## Run an e2e test

There are a few example jobs in `deployment/jobs` which can be tweaked to point
to your ingress and run:

    kubectl create -f jobs/e2e-test-job.yaml


## To view the celery monitor:

Find the pod that the monitor is running on then forward the port:

    kubectl port-forward entityservice-monitor-4045544268-s34zl 8888:8888

## To add the Route53 DNS record

Find out the Amazon Load Balancer address:

    kubectl describe service entityservice-api

Add a CNAME record to aws.


# Helm bits and bobs:

Updating a running chart is usually straight forward. For example if the
release is called `eerie-gecko` and you are in the `deployment/entity-service`
directory:

    helm upgrade eerie-gecko .