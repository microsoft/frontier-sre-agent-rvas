# syntax=docker/dockerfile:1

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

COPY . .
RUN rm -rf \
        src/Alyio.McpMssql/bin \
        src/Alyio.McpMssql/obj \
        test/Alyio.McpMssql.Tests/bin \
        test/Alyio.McpMssql.Tests/obj \
    && dotnet restore src/Alyio.McpMssql/Alyio.McpMssql.csproj \
        --force-evaluate \
    && dotnet restore test/Alyio.McpMssql.Tests/Alyio.McpMssql.Tests.csproj \
        --force-evaluate
RUN if ! dotnet test test/Alyio.McpMssql.Tests/Alyio.McpMssql.Tests.csproj \
        --configuration Release \
        --framework net10.0 \
        --no-restore \
        --filter "FullyQualifiedName~.Unit." \
        --verbosity minimal \
        > /tmp/test.log 2>&1; \
    then \
        LC_ALL=C tr -cd '\11\12\15\40-\176' < /tmp/test.log; \
        exit 1; \
    fi \
    && tail -n 20 /tmp/test.log | LC_ALL=C tr -cd '\11\12\15\40-\176'
RUN dotnet publish src/Alyio.McpMssql/Alyio.McpMssql.csproj \
    --configuration Release \
    --framework net10.0 \
    --no-restore \
    --output /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app

ENV ASPNETCORE_URLS=http://+:8080 \
    DOTNET_EnableDiagnostics=0 \
    MCPMSSQL_TRANSPORT=http \
    MCPMSSQL_REQUIRE_AZURE_MANAGED_IDENTITY=true

EXPOSE 8080

COPY --from=build /app/publish .

USER $APP_UID

ENTRYPOINT ["dotnet", "Alyio.McpMssql.dll"]
