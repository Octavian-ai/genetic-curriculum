# Curriculum training a Differentiable Neural Computer using Population Based Training

Welcome to this installment of DeepMind mashup.

For background, read up on [Differentiable Neural Computers](https://deepmind.com/blog/differentiable-neural-computers/) and [Population Based Training](https://deepmind.com/blog/population-based-training-neural-networks/).


To train run two seperate processes:
```shell
python -m src.manage --group my_name
python -m src.drone --group my_name
```


To test:
```shell
./test.sh
```


## Deploying to Kubernetes

```
kubectl create serviceaccount default --namespace default
kubectl create clusterrolebinding default-cluster-rule --clusterrole=cluster-admin --serviceaccount=default:default
```

To see dashboard:
```
gcloud config config-helper --format=json | jq --raw-output '.credential.access_token'
kubectl proxy
```