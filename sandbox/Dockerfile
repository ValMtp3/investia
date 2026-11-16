# Sidecar de sandboxing Investia (23i) — binaire Go 100 % statique.
# L'image runtime embarque python3 (exécuté par le sidecar dans la sandbox).
FROM golang:1.27-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/sidecar ./cmd/sidecar

FROM python:3.12-slim-bookworm
COPY --from=build /out/sidecar /usr/local/bin/sidecar
RUN useradd -m -u 65534 sandbox && mkdir -p /run/investia && chown sandbox /run/investia
USER sandbox
ENV INVESTIA_SANDBOX_SOCK=/run/investia/sandbox.sock
EXPOSE 0
ENTRYPOINT ["/usr/local/bin/sidecar"]
