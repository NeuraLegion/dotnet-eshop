FROM buildpack-deps:bookworm AS build
WORKDIR /src

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        libc6 \
        libgcc-s1 \
        libicu72 \
        libssl3 \
        libstdc++6 \
        tzdata \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

ENV DOTNET_INSTALL_DIR=/usr/share/dotnet
ENV PATH="${DOTNET_INSTALL_DIR}:${PATH}"
ENV DOTNET_ROLL_FORWARD=Major
ENV DOTNET_NOLOGO=1
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
ENV DOTNET_GENERATE_ASPNET_CERTIFICATE=false
ENV ASPNETCORE_URLS=http://+:19888
ENV ESHOP_USE_HTTP_ENDPOINTS=1

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && chmod +x /tmp/dotnet-install.sh \
    && /tmp/dotnet-install.sh --version 10.0.100-rc.1.25451.107 --install-dir "${DOTNET_INSTALL_DIR}" \
    && rm -f /tmp/dotnet-install.sh \
    && dotnet --info

COPY . .

RUN dotnet restore src/eShop.AppHost/eShop.AppHost.csproj
RUN dotnet publish src/eShop.AppHost/eShop.AppHost.csproj -c Release -o /app/publish /p:UseAppHost=false \
    && test -f /app/publish/eShop.AppHost.dll

FROM debian:bookworm-slim AS runtime
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libc6 \
        libgcc-s1 \
        libicu72 \
        libssl3 \
        libstdc++6 \
        tzdata \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

ENV DOTNET_INSTALL_DIR=/usr/share/dotnet
ENV PATH="${DOTNET_INSTALL_DIR}:${PATH}"
ENV DOTNET_ROLL_FORWARD=Major
ENV DOTNET_NOLOGO=1
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
ENV DOTNET_GENERATE_ASPNET_CERTIFICATE=false
ENV ASPNETCORE_URLS=http://+:19888
ENV ESHOP_USE_HTTP_ENDPOINTS=1

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && chmod +x /tmp/dotnet-install.sh \
    && /tmp/dotnet-install.sh --version 10.0.100-rc.1.25451.107 --install-dir "${DOTNET_INSTALL_DIR}" \
    && rm -f /tmp/dotnet-install.sh \
    && dotnet --info

COPY --from=build /app/publish/ ./

EXPOSE 19888

CMD ["dotnet", "eShop.AppHost.dll"]
