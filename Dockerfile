# FROM gcr.io/tensorflow/tensorflow:1.7.0-rc0-py3
FROM gcr.io/google-appengine/python
RUN pip install --upgrade pip
RUN pip install pipenv

ADD source /source
WORKDIR /source
RUN pipenv install --verbose --skip-lock

CMD ["pipenv" "run", "python -m experiment.k8"]