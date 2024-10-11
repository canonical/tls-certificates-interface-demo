#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


"""Charm the service."""

import logging
from typing import Optional

import ops
from charms.tls_certificates_interface.v4.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    Mode,
    PrivateKey,
    TLSCertificatesRequiresV4,
)

logger = logging.getLogger(__name__)

CERTS_DIR_PATH = "/etc/nginx"
PRIVATE_KEY_NAME = "nginx.key"
CERTIFICATE_NAME = "nginx.pem"
CONFIG_DIR_PATH = "/etc/nginx/conf.d"
CONFIG_FILE_NAME = "default.conf"
HTTP_PORT = 8080


class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.container = self.unit.get_container("nginx")
        self.unit.set_ports(HTTP_PORT)
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=[self._get_certificate_request_attributes()],
            mode=Mode.UNIT,
        )
        framework.observe(self.on["nginx"].pebble_ready, self._configure)
        framework.observe(self.on.config_changed, self._configure)
        framework.observe(self.certificates.on.certificate_available, self._configure)
        framework.observe(self.on.collect_unit_status, self._on_collect_status)

    def _on_collect_status(self, event: ops.CollectStatusEvent):
        if not self.unit.is_leader():
            event.add_status(ops.BlockedStatus("scaling is not supported"))
            return
        if not self._relation_created("certificates"):
            event.add_status(ops.BlockedStatus("certificates integration not created"))
            return
        if not self.container.can_connect():
            event.add_status(ops.WaitingStatus("can't connect to container yet"))
            return
        if not self._nginx_service_is_running():
            event.add_status(ops.WaitingStatus("nginx service not yet running"))
            return
        event.add_status(ops.ActiveStatus())

    def _configure(self, _: ops.EventBase):
        if not self.container.can_connect():
            return
        if not self._relation_created("certificates"):
            return
        if not self._certificate_is_available():
            return
        certificate_update_required = self._check_and_update_certificate()
        desired_config_file = self._generate_config_file()
        if config_update_required := self._is_config_update_required(desired_config_file):
            self._push_config_file(content=desired_config_file)
        should_restart = config_update_required or certificate_update_required
        self._configure_pebble(restart=should_restart)

    def _get_certificate_request_attributes(self) -> CertificateRequestAttributes:
        return CertificateRequestAttributes(common_name="example.com")

    def _relation_created(self, relation_name: str) -> bool:
        return bool(self.model.relations.get(relation_name))

    def _certificate_is_available(self) -> bool:
        cert, key = self.certificates.get_assigned_certificate(
            certificate_request=self._get_certificate_request_attributes()
        )
        return bool(cert and key)

    def _check_and_update_certificate(self) -> bool:
        """Check if the certificate or private key needs an update and perform the update.

        This method retrieves the currently assigned certificate and private key associated with
        the charm's TLS relation. It checks whether the certificate or private key has changed
        or needs to be updated. If an update is necessary, the new certificate or private key is
        stored.

        Returns:
            bool: True if either the certificate or the private key was updated, False otherwise.
        """
        provider_certificate, private_key = self.certificates.get_assigned_certificate(
            certificate_request=self._get_certificate_request_attributes()
        )
        if not provider_certificate or not private_key:
            logger.debug("Certificate or private key is not available")
            return False
        if certificate_update_required := self._is_certificate_update_required(
            provider_certificate.certificate
        ):
            self._store_certificate(certificate=provider_certificate.certificate)
        if private_key_update_required := self._is_private_key_update_required(private_key):
            self._store_private_key(private_key=private_key)
        return certificate_update_required or private_key_update_required

    def _is_certificate_update_required(self, certificate: Certificate) -> bool:
        return self._get_existing_certificate() != certificate

    def _is_private_key_update_required(self, private_key: PrivateKey) -> bool:
        return self._get_existing_private_key() != private_key

    def _get_existing_certificate(self) -> Optional[Certificate]:
        return self._get_stored_certificate() if self._certificate_is_stored() else None

    def _get_existing_private_key(self) -> Optional[PrivateKey]:
        return self._get_stored_private_key() if self._private_key_is_stored() else None

    def _certificate_is_stored(self) -> bool:
        return self.container.exists(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}")

    def _private_key_is_stored(self) -> bool:
        return self.container.exists(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}")

    def _get_stored_certificate(self) -> Certificate:
        cert_string = str(self.container.pull(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}").read())
        return Certificate.from_string(cert_string)

    def _get_stored_private_key(self) -> PrivateKey:
        key_string = str(self.container.pull(path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}").read())
        return PrivateKey.from_string(key_string)

    def _store_certificate(self, certificate: Certificate) -> None:
        """Store certificate in workload."""
        self.container.push(path=f"{CERTS_DIR_PATH}/{CERTIFICATE_NAME}", source=str(certificate))
        logger.info("Pushed certificate pushed to workload")

    def _store_private_key(self, private_key: PrivateKey) -> None:
        """Store private key in workload."""
        self.container.push(
            path=f"{CERTS_DIR_PATH}/{PRIVATE_KEY_NAME}",
            source=str(private_key),
        )
        logger.info("Pushed private key to workload")

    def _configure_pebble(self, restart: bool):
        plan = self.container.get_plan()
        if plan.services != self._pebble_layer.services:
            self.container.add_layer("nginx", self._pebble_layer, combine=True)
            self.container.replan()
            logger.info("New layer added: %s", self._pebble_layer)
        if restart:
            self.container.restart("nginx")
            logger.info("Restarted container %s", "nginx")
            return
        self.container.replan()

    def _generate_config_file(self) -> str:
        with open(f"src/{CONFIG_FILE_NAME}") as f:
            config_file = f.read()
        return config_file

    def _is_config_update_required(self, content: str) -> bool:
        if not self._config_file_is_written() or not self._config_file_content_matches(
            content=content
        ):
            return True
        return False

    def _config_file_is_written(self) -> bool:
        return bool(self.container.exists(f"{CONFIG_DIR_PATH}/{CONFIG_FILE_NAME}"))

    def _push_config_file(self, content: str) -> None:
        self.container.push(
            path=f"{CONFIG_DIR_PATH}/{CONFIG_FILE_NAME}",
            source=content,
        )
        logger.info("Pushed %s config file", CONFIG_FILE_NAME)

    def _config_file_content_matches(self, content: str) -> bool:
        if not self.container.exists(path=f"{CONFIG_DIR_PATH}/{CONFIG_FILE_NAME}"):
            return False
        existing_content = self.container.pull(path=f"{CONFIG_DIR_PATH}/{CONFIG_FILE_NAME}")
        if existing_content.read() != content:
            return False
        return True

    def _nginx_service_is_running(self) -> bool:
        if not self.container.can_connect():
            return False
        try:
            service = self.container.get_service("nginx")
        except ops.ModelError:
            return False
        return service.is_running()

    @property
    def _pebble_layer(self) -> ops.pebble.Layer:
        """Return a dictionary representing a Pebble layer."""
        return ops.pebble.Layer(
            {
                "summary": "nginx layer",
                "description": "pebble config layer for nginx",
                "services": {
                    "nginx": {
                        "override": "replace",
                        "summary": "nginx",
                        "command": "nginx -g 'daemon off;'",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":  # pragma: nocover
    ops.main(TlsCertificatesInterfaceDemoCharm)  # type: ignore
