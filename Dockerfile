FROM python:3.14
LABEL authors="RMS"

RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install -y moreutils

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
