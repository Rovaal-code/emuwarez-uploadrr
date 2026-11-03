"""Unit tests for emuwarez_uploadrr/services/integration_tests.py (Phase 10C).

All HTTP calls are mocked — no real internet traffic.
"""
from __future__ import annotations

from unittest.mock import patch

from tests.http_falso import falla_conexion, respuesta, tiempo_agotado

from emuwarez_uploadrr.services.integration_tests import (
    test_arr_connection as svc_test_arr,
    test_emuwarez_connection as svc_test_emu,
    test_tmdb_connection as svc_test_tmdb,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status: int = 200):
    return respuesta(status)


def _http_error(code: int):
    return respuesta(code)


def _url_error(reason: str):
    return falla_conexion(reason)


def _timeout_url_error():
    return tiempo_agotado()


# ---------------------------------------------------------------------------
# svc_test_tmdb
# ---------------------------------------------------------------------------

class TestTmdbConnection:
    def test_not_configured_no_key(self):
        result = svc_test_tmdb(api_key=None)
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert result["service"] == "tmdb"

    def test_not_configured_empty_key(self):
        result = svc_test_tmdb(api_key="   ")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    def test_success(self, http_falso):
        http_falso.responde(_mock_response(200))
        result = svc_test_tmdb(api_key="validkey123")
        assert result["ok"] is True
        assert result["status"] == "connected"
        assert result["service"] == "tmdb"

    def test_invalid_key_401(self, http_falso):
        http_falso.responde(_http_error(401))
        result = svc_test_tmdb(api_key="badkey")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_invalid_key_403(self, http_falso):
        http_falso.responde(_http_error(403))
        result = svc_test_tmdb(api_key="badkey")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_connection_error_other_http(self, http_falso):
        http_falso.responde(_http_error(500))
        result = svc_test_tmdb(api_key="anykey")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_timeout(self, http_falso):
        http_falso.responde(_timeout_url_error())
        result = svc_test_tmdb(api_key="anykey")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_url_error_network(self, http_falso):
        http_falso.responde(_url_error("Name or service not known"))
        result = svc_test_tmdb(api_key="anykey")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_reads_key_from_db_when_none(self, tmp_path):
        """api_key=None → reads from DB (settings key 'tmdb.api_key')."""
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(tmp_path / "test.db")
        init_db(conn)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('tmdb.api_key', '')")
        conn.commit()
        result = svc_test_tmdb(api_key=None, conn=conn)
        assert result["status"] == "not_configured"

    def test_full_key_never_in_response(self, http_falso):
        """Full API key must not appear in the result dict."""
        import json
        secret = "supersecret_tmdb_key_99999"
        http_falso.responde(_url_error("Name or service not known"))
        result = svc_test_tmdb(api_key=secret)
        serialised = json.dumps(result)
        assert secret not in serialised


# ---------------------------------------------------------------------------
# svc_test_emu
# ---------------------------------------------------------------------------

class TestEmuwarezConnection:
    def test_not_configured_no_key(self):
        result = svc_test_emu(api_key=None)
        assert result["ok"] is False
        assert result["status"] == "not_configured"
        assert result["service"] == "emuwarez"

    def test_invalid_url(self):
        result = svc_test_emu(api_key="key123", base_url="not-a-url")
        assert result["ok"] is False
        assert result["status"] == "invalid_url"

    def test_http_remoto_se_rechaza_sin_enviar_la_clave(self, http_falso):
        result = svc_test_emu(api_key="key123", base_url="http://emu-warez.com")
        assert result["ok"] is False
        assert result["status"] == "insecure_url"
        assert "key123" not in str(result)
        assert http_falso.peticiones == []

    def test_http_en_loopback_se_admite(self, http_falso):
        http_falso.responde(_mock_response(200))
        result = svc_test_emu(api_key="key123", base_url="http://localhost:8080")
        assert result["ok"] is True

    def test_success(self, http_falso):
        http_falso.responde(_mock_response(200))
        result = svc_test_emu(api_key="key123", base_url="https://emu-warez.com")
        assert result["ok"] is True
        assert result["status"] == "connected"

    def test_invalid_key_401(self, http_falso):
        http_falso.responde(_http_error(401))
        result = svc_test_emu(api_key="badkey", base_url="https://emu-warez.com")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    def test_timeout(self, http_falso):
        http_falso.responde(_timeout_url_error())
        result = svc_test_emu(api_key="key", base_url="https://emu-warez.com")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_connection_error(self, http_falso):
        http_falso.responde(_url_error("Connection refused"))
        result = svc_test_emu(api_key="key", base_url="https://emu-warez.com")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    def test_defaults_to_emuwarez_base_url(self, http_falso):
        """base_url defaults to https://emu-warez.com when not provided."""
        http_falso.responde(_mock_response(200))
        result = svc_test_emu(api_key="key123")
        assert result["ok"] is True
        called_url = str(http_falso.ultima.url)
        assert "emu-warez.com" in called_url

    def test_full_key_never_in_response(self):
        import json
        secret = "emuwarez_secret_key_00000"
        result = svc_test_emu(api_key=secret, base_url="badurl")
        serialised = json.dumps(result)
        assert secret not in serialised

    def test_rate_limited_second_call_within_a_minute(self, http_falso, tmp_path):
        """A second live probe within 60s is throttled without hitting the network."""
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(tmp_path / "test.db")
        init_db(conn)
        http_falso.responde(_mock_response(200))

        first = svc_test_emu(api_key="key123", base_url="https://emu-warez.com", conn=conn)
        assert first["ok"] is True
        assert len(http_falso.peticiones) == 1

        second = svc_test_emu(api_key="key123", base_url="https://emu-warez.com", conn=conn)
        assert second["ok"] is False
        assert second["status"] == "rate_limited"
        assert second["details"]["wait_seconds"] > 0
        # crucially, the throttled call never reached the network
        assert len(http_falso.peticiones) == 1

    def test_rate_limit_allows_again_after_interval(self, http_falso, tmp_path):
        """Once the interval has elapsed, a new probe is allowed again."""
        import datetime as dt
        from emuwarez_uploadrr.database import connect, init_db, set_state
        from emuwarez_uploadrr.services.integration_tests import (
            EMU_TEST_STATE_KEY,
            MIN_EMU_TEST_SECONDS,
        )
        conn = connect(tmp_path / "test.db")
        init_db(conn)
        http_falso.responde(_mock_response(200))

        stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=MIN_EMU_TEST_SECONDS + 1)
        set_state(conn, EMU_TEST_STATE_KEY, stale.isoformat())

        result = svc_test_emu(api_key="key123", base_url="https://emu-warez.com", conn=conn)
        assert result["ok"] is True
        assert len(http_falso.peticiones) == 1

    def test_no_mantiene_la_base_bloqueada_durante_la_peticion(self, http_falso, tmp_path):
        """La marca de «una prueba por minuto» se confirma antes de ir a la red: si no, el bloqueo de escritura
        dura lo que tarde eMuwarez (hasta el timeout) y el resto de la aplicación falla con «database is locked»."""
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(tmp_path / "test.db")
        init_db(conn)
        otra = connect(tmp_path / "test.db")
        en_transaccion = []

        def al_pedir(request):
            en_transaccion.append(conn.in_transaction)
            otra.execute("PRAGMA busy_timeout = 0")
            otra.execute("INSERT INTO app_state(key, value) VALUES ('x', '1')")  # fallaría con la base bloqueada
            otra.commit()
            return respuesta(200)(request)

        http_falso.responde(al_pedir)
        result = svc_test_emu(api_key="key123", base_url="https://emu-warez.com", conn=conn)
        assert result["ok"] is True
        assert en_transaccion == [False]

    def test_con_clave_nueva_usa_la_url_guardada(self, http_falso, tmp_path):
        """Probar una clave nueva (Ajustes, Setup) sin url explícita lee la url de la base, sin UnboundLocalError."""
        from emuwarez_uploadrr.database import connect, init_db
        from emuwarez_uploadrr.services.settings import set_setting
        conn = connect(tmp_path / "test.db")
        init_db(conn)
        set_setting(conn, "emu.endpoint_url", "https://otra.example")
        conn.commit()
        http_falso.responde(_mock_response(200))

        result = svc_test_emu(api_key="clave-nueva", conn=conn, enforce_rate_limit=False)
        assert result["ok"] is True
        assert "otra.example" in str(http_falso.ultima.url)

    def test_not_configured_is_not_throttled(self, http_falso, tmp_path):
        """Pre-network failures (no key) must never consume/trigger the rate limit."""
        from emuwarez_uploadrr.database import connect, init_db, get_state
        from emuwarez_uploadrr.services.integration_tests import EMU_TEST_STATE_KEY
        conn = connect(tmp_path / "test.db")
        init_db(conn)

        result = svc_test_emu(api_key=None, base_url="https://emu-warez.com", conn=conn)
        assert result["status"] == "not_configured"
        # no timestamp recorded, no network call
        assert get_state(conn, EMU_TEST_STATE_KEY) is None
        assert len(http_falso.peticiones) == 0


# ---------------------------------------------------------------------------
# svc_test_arr
# ---------------------------------------------------------------------------

class TestArrConnection:
    def test_invalid_kind(self):
        result = svc_test_arr(kind="jellyfin", base_url="http://x", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "invalid_kind"

    def test_invalid_kind_none(self):
        result = svc_test_arr(kind=None, base_url="http://x", api_key="k")  # type: ignore[arg-type]
        assert result["ok"] is False
        assert result["status"] == "invalid_kind"

    def test_not_configured_missing_url(self):
        result = svc_test_arr(kind="radarr", base_url="", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    def test_not_configured_missing_key(self):
        result = svc_test_arr(kind="sonarr", base_url="http://localhost:8989", api_key="  ")
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_success_radarr(self, mock_req):
        mock_req.return_value = {"version": "5.3.6", "appName": "Radarr"}
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="abc123")
        assert result["ok"] is True
        assert result["status"] == "connected"
        assert result["service"] == "radarr"
        assert result["details"]["version"] == "5.3.6"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_success_sonarr(self, mock_req):
        mock_req.return_value = {"version": "4.0.1"}
        result = svc_test_arr(kind="sonarr", base_url="http://localhost:8989", api_key="xyz")
        assert result["ok"] is True
        assert result["service"] == "sonarr"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_invalid_key(self, mock_req):
        from emuwarez_uploadrr.integrations.arr_base import ArrAuthError
        mock_req.side_effect = ArrAuthError("Autenticación fallida")
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="wrong")
        assert result["ok"] is False
        assert result["status"] == "invalid_key"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_connection_error(self, mock_req):
        from emuwarez_uploadrr.integrations.arr_base import ArrConnectionError
        mock_req.side_effect = ArrConnectionError("No se pudo conectar")
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "connection_error"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_timeout_detected(self, mock_req):
        from emuwarez_uploadrr.integrations.arr_base import ArrConnectionError
        mock_req.side_effect = ArrConnectionError("Timeout conectando con http://x")
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key="k")
        assert result["ok"] is False
        assert result["status"] == "timeout"

    def test_prepends_http_if_missing_scheme(self):
        """URLs without scheme get http:// prepended before making the call."""
        with patch("emuwarez_uploadrr.integrations.arr_base.arr_request") as mock_req,                 patch("emuwarez_uploadrr.services.integration_tests._arr_content_visibility",
                      return_value={"visible": True, "roots": []}):
            mock_req.return_value = {"version": "5.0"}
            result = svc_test_arr(kind="radarr", base_url="192.168.1.10:7878", api_key="k")
            assert result["ok"] is True
            called_url = mock_req.call_args[0][1]
            assert called_url.startswith("http://")

    def test_full_key_never_in_response(self):
        import json
        secret = "radarr_secret_api_key_xyz"
        result = svc_test_arr(kind="radarr", base_url="http://localhost:7878", api_key=secret)
        # Will be a failure (no real server) but key must not appear in result
        serialised = json.dumps(result)
        assert secret not in serialised

    def test_instance_id_without_conn_fails(self):
        result = svc_test_arr(instance_id=1)
        assert result["ok"] is False
        assert result["status"] == "unexpected_error"

    def test_instance_id_not_found(self, isolated_db):
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(isolated_db / "emuwarez_uploadrr.db")
        init_db(conn)
        result = svc_test_arr(instance_id=999, conn=conn)
        assert result["ok"] is False
        assert result["status"] == "not_configured"

    @patch("emuwarez_uploadrr.integrations.arr_base.arr_request")
    def test_instance_id_uses_saved_instance(self, mock_req, isolated_db):
        from emuwarez_uploadrr.database import connect, init_db
        from emuwarez_uploadrr.services.instances import add_instance

        conn = connect(isolated_db / "emuwarez_uploadrr.db")
        init_db(conn)
        instance_id = add_instance(conn, "radarr", "Radarr saved", "http://localhost:7878", "saved-key")

        mock_req.return_value = {"version": "5.3.6"}
        result = svc_test_arr(instance_id=instance_id, conn=conn)
        assert result["ok"] is True
        assert result["service"] == "radarr"
        assert result["details"]["version"] == "5.3.6"
        assert result["details"]["instance_id"] == instance_id
