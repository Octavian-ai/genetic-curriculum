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