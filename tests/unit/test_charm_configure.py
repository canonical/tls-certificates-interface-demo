# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import os
import tempfile
from unittest.mock import patch

import ops
import pytest
import scenario

from charm import TlsCertificatesInterfaceDemoCharm
from tests.unit.certificates_helpers import example_cert_and_key


class TestCharmCollectStatus:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=TlsCertificatesInterfaceDemoCharm,
        )

    @patch(
        "charms.tls_certificates_interface.v4.tls_certificates.TLSCertificatesRequiresV4.get_assigned_certificate"
    )
    def test_given_can_connect_when_configure_then_pebble_plan_is_applied(
        self, mock_get_assigned_certificate
    ):
        tls_integration = scenario.Relation(endpoint="certificates", interface="tls-certificates")
        etc_mount = scenario.Mount(
            location="/etc/nginx/conf.d",
            source=tempfile.mkdtemp(),
        )
        container = scenario.Container(
            name="nginx",
            can_connect=True,
            mounts={"etc": etc_mount},
        )
        state_in = scenario.State(
            leader=True,
            containers=[container],
            relations=[tls_integration],
        )
        provider_certificate, private_key = example_cert_and_key(
            tls_relation_id=tls_integration.id
        )
        mock_get_assigned_certificate.return_value = provider_certificate, private_key

        state_out = self.ctx.run(self.ctx.on.pebble_ready(container), state_in)

        assert state_out.containers == {
            scenario.Container(
                name="nginx",
                can_connect=True,
                mounts={"etc": etc_mount},
                layers={
                    "nginx": ops.pebble.Layer(
                        {
                            "summary": "nginx layer",
                            "description": "pebble config layer for nginx",
                            "services": {
                                "nginx": {
                                    "summary": "nginx",
                                    "startup": "enabled",
                                    "override": "replace",
                                    "command": "nginx -g 'daemon off;'",
                                }
                            },
                        }
                    )
                },
                service_statuses={"nginx": ops.pebble.ServiceStatus.ACTIVE},
            )
        }

    @patch(
        "charms.tls_certificates_interface.v4.tls_certificates.TLSCertificatesRequiresV4.get_assigned_certificate"
    )
    def test_given_can_connect_when_configure_then_config_file_rendered_and_pushed_correctly(  # noqa: E501
        self, mock_get_assigned_certificate
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            tls_integration = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            etc_mount = scenario.Mount(
                location="/etc/nginx/conf.d",
                source=tempdir,
            )
            container = scenario.Container(
                name="nginx",
                can_connect=True,
                mounts={"etc": etc_mount},
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[tls_integration],
            )
            provider_certificate, private_key = example_cert_and_key(
                tls_relation_id=tls_integration.id
            )
            mock_get_assigned_certificate.return_value = provider_certificate, private_key

            self.ctx.run(self.ctx.on.pebble_ready(container), state_in)

            with open("tests/unit/expected.conf", "r") as f:
                expected_config = f.read().strip()

            with open(f"{tempdir}/default.conf", "r") as f:
                assert f.read() == expected_config

    @patch(
        "charms.tls_certificates_interface.v4.tls_certificates.TLSCertificatesRequiresV4.get_assigned_certificate"
    )
    def test_given_config_file_already_pushed_when_configure_then_config_file_not_pushed_again(
        self, mock_get_assigned_certificate
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            tls_integration = scenario.Relation(
                endpoint="certificates", interface="tls-certificates"
            )
            etc_mount = scenario.Mount(
                location="/etc/nginx/conf.d",
                source=tempdir,
            )
            container = scenario.Container(
                name="nginx",
                can_connect=True,
                mounts={"etc": etc_mount},
            )
            state_in = scenario.State(
                leader=True,
                containers=[container],
                relations=[tls_integration],
            )
            with open("tests/unit/expected.conf", "r") as f:
                expected_config = f.read().strip()
            with open(f"{tempdir}/default.conf", "w") as f:
                f.write(expected_config)
            config_modification_time = os.stat(tempdir + "/default.conf").st_mtime
            provider_certificate, private_key = example_cert_and_key(
                tls_relation_id=tls_integration.id
            )
            mock_get_assigned_certificate.return_value = provider_certificate, private_key

            self.ctx.run(self.ctx.on.pebble_ready(container), state_in)

            with open(f"{tempdir}/default.conf", "r") as f:
                assert f.read() == expected_config
            assert os.stat(tempdir + "/default.conf").st_mtime == config_modification_time
