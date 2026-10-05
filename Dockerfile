FROM python:3.14
LABEL authors="RMS"

RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install -y moreutils

RUN pip install --no-cache-dir ollama
RUN pip install --no-cache-dir numpy
RUN pip install --no-cache-dir pandas
RUN pip install --no-cache-dir scipy
RUN pip install --no-cache-dir matplotlib
RUN pip install --no-cache-dir seaborn
RUN pip install --no-cache-dir ipykernel
RUN pip install --no-cache-dir jinja2
RUN pip install --no-cache-dir streamlit