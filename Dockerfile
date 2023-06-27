FROM jupyter/datascience-notebook:latest

USER root

# Conda configuration
RUN conda config --set allow_conda_downgrades true

# Install Python 3.9 specifically
RUN conda install python=3.9

# Run jupyter notebook when the container launches
CMD ["jupyter", "notebook", "--ip='*'", "--port=8888", "--no-browser", "--allow-root"]
