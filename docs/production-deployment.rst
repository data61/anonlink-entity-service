Production deployment
=====================

Production deployment assumes a multi node `Kubernetes <https://kubernetes.io/docs/home/>`__
cluster.

The entity service has been deployed to kubernetes clusters on GCE and
AWS. The system has been designed to scale across multiple nodes
and handle node failure without data loss.


.. figure:: _static/deployment.png
   :alt: Entity Service Kubernetes Deployment
   :width: 800 px

At a high level the main custom components are:

- **ES App** - a gunicorn/flask backend web service hosts the REST api
- **Entity Match Worker** instances - uses celery for task scheduling

The components that are used in support are:

- postgresql database holds all match metadata
- redis is used for the celery job queue and as a cache
- minio object store stores the raw CLKs and result files
- nginx provides upload buffering, request rate limiting.
- an ingress controller (e.g. traefik) provides TLS termination


The rest of this document goes into how to deploy in a production setting.


Bring up a Kubernetes cluster:
------------------------------

Creating a Kubernetes cluster is out of scope for this documentation.
For AWS there is a good tutorial `here <https://github.com/coreos/kube-aws>`__.

**Hardware requirements**

Recommended AWS worker `instance type <https://aws.amazon.com/ec2/instance-types/>`__
is ``r3.4xlarge`` - spot instances are fine as we handle node failure. The
number of nodes depends on the size of the expected jobs, as well as the
memory on each node. For testing we recommend starting with at least two nodes, with each
node having at least 8 GiB of memory and 2 vCPUs.


**Software to interact with the cluster**

You will need to install the `kubectl <https://kubernetes.io/docs/tasks/kubectl/install/>`__
command line tool, and `helm <https://github.com/kubernetes/helm>`__


Provision cluster resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Note ``kubectl`` uses the same interface to provision all types of
resource. Before deploying the entity service we need to provision a few other
things on the cluster. An existing kubernetes cluster may already have
these.

::

    kubectl create -f aws-storage.yaml -f n1-coreos-secret.yaml


**Dynamically provisioned storage**

When pods require persistent storage this can be dynamically
provided by the cluster. The default settings (in ``values.yaml``)
assumes the existence of a ``"slow"`` ``storageClass``.

For a cluster on AWS the ``aws-storage.yaml`` resource will dynamically
provision elastic block store volumes.

**Docker login credentials**

This secret allows nodes to pull from our private quay.io repository:

``n1-coreos-secret.yaml``


Helm
~~~~

The system has been packaged using `helm <https://github.com/kubernetes/helm>`__,
there is a program that needs to be `installed <https://github.com/kubernetes/helm/blob/master/docs/install.md>`__

At the very least you will need to install tiller into the cluster::

    helm init


Ingress Controller
~~~~~~~~~~~~~~~~~~

We assume the cluster has an ingress controller, if this isn't the case
we will have to add one. We suggest using `Traefik <https://traefik.io/>`__.

Deploy the `traefik ingress
controller <https://docs.traefik.io/user-guide/kubernetes/>`__ into the
kube-system namespace with:

::

    helm install --name traefik --namespace kube-system --values traefik.yaml stable/traefik

Note you can update the traefik.yaml file and upgrade in place with:

::

    helm upgrade traefik --namespace kube-system --values traefik.yaml stable/traefik



Deploy the system
-----------------

**Helm** can be used to easily deploy the system to a kubernetes cluster.

From the `deployment/entity-service` directory pull the dependencies:

::

    helm dependency update

Carefully read through and adjust the ``values.yaml`` file to your deployment.

For example set the domain by changing ``api.domain``, change the workers' cpu \
and memory limits in ``workers.resources``.



Install the whole system

::

    cd entity-service
    helm install . --name="n1entityservice"

This can take around 10 minutes the first time you deploy to a new cluster.

Run an end to end test
----------------------

::

    kubectl create -f jobs/e2e-test-job.yaml

To view the celery monitor:
---------------------------

Find the pod that the monitor is running on then forward the port:

::

    kubectl port-forward entityservice-monitor-4045544268-s34zl 8888:8888

To add the Route53 DNS record
-----------------------------

Find out the Amazon Load Balancer address:

::

    kubectl describe service entityservice-api

Add a CNAME record to aws.

Helm bits and bobs:
-------------------

Updating a running chart is usually straight forward. For example if the
release is called ``eerie-gecko`` and you are in the
``deployment/entity-service`` directory:

::

    helm upgrade eerie-gecko .

