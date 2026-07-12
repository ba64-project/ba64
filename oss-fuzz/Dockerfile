FROM gcr.io/oss-fuzz-base/base-builder-python
RUN git clone --depth 1 https://github.com/ba64-project/ba64 ba64
WORKDIR ba64
COPY build.sh $SRC/
