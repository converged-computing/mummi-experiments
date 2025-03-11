ARG tag=createsims
FROM 633731392008.dkr.ecr.us-east-1.amazonaws.com/mini-mummi:${tag}

# docker build -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector .
# docker buildx build --platform linux/arm64 --build-arg tag=createsims-arm --push -t ghcr.io/converged-computing/mummi-experiments:cpu-node-selector-arm .
# docker run ghcr.io/converged-computing/mummi-experiments:cpu-node-selector
# docker push ghcr.io/converged-computing/mummi-experiments:cpu-node-selector

WORKDIR /tmp/workdir/099868581
COPY structure_099868581_000000000000.gro /tmp/workdir/099868581/structure_099868581.gro
COPY ./entrypoint.sh /entrypoint.sh
WORKDIR /tmp/workdir
ENTRYPOINT ["/bin/bash"]
CMD ["/entrypoint.sh"]

