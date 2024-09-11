# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import ops
import pytest
import scenario
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import TlsCertificatesInterfaceDemoCharm


class TestCharmCollectStatus:
    @pytest.fixture(autouse=True)
    def context(self):
        self.ctx = scenario.Context(
            charm_type=TlsCertificatesInterfaceDemoCharm,
        )

    def test_given_unit_is_not_leader_when_collect_unit_status_then_status_is_blocked(self):
        state_in = scenario.State(leader=False)

        state_out = self.ctx.run(self.ctx.on.collect_unit_status(), state_in)

        assert state_out.unit_status == BlockedStatus("scaling is not supported")

    def test_given_cant_connect_to_container_when_collect_unit_status_then_status_is_waiting(self):
        container = scenario.Container(name="nginx", can_connect=False)
        state_in = scenario.State(leader=True, containers=[container])

        state_out = self.ctx.run(self.ctx.on.collect_unit_status(), state_in)

        assert state_out.unit_status == WaitingStatus("can't connect to container yet")

    def test_given_nginx_service_not_running_when_collect_unit_status_then_status_is_waiting(
        self,
    ):
        container = scenario.Container(name="nginx", can_connect=True)
        state_in = scenario.State(leader=True, containers=[container])

        state_out = self.ctx.run(self.ctx.on.collect_unit_status(), state_in)

        assert state_out.unit_status == WaitingStatus("nginx service not yet running")

    def test_given_nginx_service_running_when_collect_unit_status_then_status_is_active(self):
        container = scenario.Container(
            name="nginx",
            can_connect=True,
            service_statuses={"nginx": ops.pebble.ServiceStatus.ACTIVE},
            layers={"nginx": ops.pebble.Layer({"services": {"nginx": {}}})},
        )
        state_in = scenario.State(leader=True, containers=[container])

        state_out = self.ctx.run(self.ctx.on.collect_unit_status(), state_in)

        assert state_out.unit_status == ActiveStatus()
