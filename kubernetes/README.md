

# Bring up a cluster:

Have at least two nodes, spot instances are fine.

https://github.com/coreos/kube-aws


# Provision cluster resources

`kubectl` uses the same interface to provision all types of resource:

    kubectl create -f some-resource.yaml

Before deploying the entity service we need to provision a few other
things on the cluster.

    kubectl create -f aws-storage.yaml -f n1-coreos-secret.yaml


## Dynamically provisioned storage:

When pods require persistent storage this can either be manually provided,
or dynamically.

`aws-storage.yaml`

## Docker login credentials

Add secret to enable pulling from private quay.io repository:

`n1-coreos-secret.yaml`


# Deploy the entity service

    cd entityservice
    kubectl create -f entityservice/db/volume-claim.yaml
    kubectl create -f db/postgres-service.yaml -f db/postgres-deployment.yaml
    kubectl create -f redis
    kubectl create -f worker
    kubectl create -f monitor
    kubectl create -f api


## Jupyter Notebook (optional)

`n1-py-notebook.yaml`