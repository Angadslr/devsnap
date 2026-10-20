from devsnap.config import ServiceConfig
from devsnap.supervisor.env_injector import resolve_environment_variables


def test_resolve_environment_variables():
    svc = ServiceConfig(
        cmd="npx expo start",
        inject_env={
            "EXPO_PUBLIC_API_URL": "$services.backend.tunnel_url",
            "PROXY_URL": "$services.backend.tunnel_url/graphql",
            "STATIC_VAR": "production",
        },
    )

    tunnels = {"backend": "https://active-tunnel-abc.trycloudflare.com"}
    resolved = resolve_environment_variables(svc, tunnels, base_env={"BASE_KEY": "123"})

    assert resolved["BASE_KEY"] == "123"
    assert resolved["EXPO_PUBLIC_API_URL"] == "https://active-tunnel-abc.trycloudflare.com"
    assert resolved["PROXY_URL"] == "https://active-tunnel-abc.trycloudflare.com/graphql"
    assert resolved["STATIC_VAR"] == "production"
