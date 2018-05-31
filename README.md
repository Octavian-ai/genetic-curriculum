# Curriculum training a Differentiable Neural Computer using Population Based Training

Welcome to this installment of DeepMind mashup.

For background, read up on [Differentiable Neural Computers](https://deepmind.com/blog/differentiable-neural-computers/) and [Population Based Training](https://deepmind.com/blog/population-based-training-neural-networks/).


### Prerequisites

- You need to have an AMQP queue server (the default is localhost)


### Run local:

To run the system locally as single process:
```shell
pipenv install
pipenv shell

python -m experiment.k8 --master-works
```


To test:
```shell
pipenv shell
./script/test.sh
```


## Deploying to Kubernetes (A cheatsheet of K8 runes)

### Install RabitMQ

- Install Helm
- Initialise Helm on your cluster as per their docs

Give helm permissions on GKE:
```
kubectl create clusterrolebinding --user system:serviceaccount:kube-system:default kube-system-cluster-admin --clusterrole cluster-admin
```

Install a queue:
```
helm install --name one --set rabbitmq.username=admin,rabbitmq.password=secretpassword,rabbitmq.erlangCookie=secretcookie     stable/rabbitmq
```

Check the console output to get the AMPQ url and password for your new queue

### Install our PBT application

Update secret.yaml to have the url to your AMQP queue.

Deploy the config:

```
kubectl create -f kubernetes/secret.yaml
kubectl create -f kubernetes/deployment.yaml
```

Set up permissions:
```
kubectl create serviceaccount default --namespace default
kubectl create clusterrolebinding default-cluster-rule --clusterrole=cluster-admin --serviceaccount=default:default
```


To see dashboard:
```
gcloud config config-helper --format=json | jq --raw-output '.credential.access_token'
kubectl proxy
```

