ARG tag=cganalysis
FROM 633731392008.dkr.ecr.us-east-1.amazonaws.com/mini-mummi:${tag}

# docker build -t ghcr.io/converged-computing/mummi-experiments:node-selector-cganalysis-cpu .

WORKDIR /tmp/workdir
COPY ./data /tmp/workdir
COPY ./entrypoint.sh /entrypoint.sh
COPY ./get_sim_lengths.py /get_sim_length.py
WORKDIR /tmp/workdir
ENTRYPOINT ["/bin/bash"]
CMD ["/entrypoint.sh"]

