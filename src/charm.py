#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


"""Charm the service."""

import logging

import ops

logger = logging.getLogger(__name__)

CONFIG_DIR_PATH = "/etc/nginx/conf.d"
CONFIG_FILE_NAME = "default.conf"
HTTP_PORT = 8080


class TlsCertificatesInterfaceDemoCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.container = self.unit.get_container("nginx")
        self.unit.set_ports(HTTP_PORT)
        framework.observe(self.on["nginx"].pebble_ready, self._configure)
        framework.observe(self.on.config_changed, self._configure)
        framework.observe(self.on.collect_unit_status, self._on_collect_status)

    def _on_collect_status(self, event: ops.CollectStatusEvent):
        if not self.unit.is_leader():
            event.add_status(ops.BlockedStatus("scaling is not supported"))
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
        desired_config_file = self._generate_config_file()
        if config_update_required := self._is_config_update_required(desired_config_file):
            self._push_config_file(content=desired_config_file)
        self._configure_pebble(restart=config_update_required)

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
