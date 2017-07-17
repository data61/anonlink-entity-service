
Install an empty jupyter notebook with helm:

    helm install . --name=icml --namespace=notebooks \
        --set ingress.domain=icml.nb.data61.xyz \
        --set passwordhash="sha1:xxx:xxx"
    
    
    