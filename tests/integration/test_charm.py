#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]

TLS_PROVIDER_CHARM_NAME = "self-signed-certificates"
TLS_PROVIDER_CHARM_CHANNEL = "latest/stable"


@pytest.mark.abort_on_fail
async def test_give_built_charm_when_deploy_then_status_is_blocked(ops_test: OpsTest, request):
    """Build the charm-under-test and deploy it.

    Assert on the unit status.
    """
    charm = Path(request.config.getoption("--charm_path")).resolve()
    resources = {"nginx-image": METADATA["resources"]["nginx-image"]["upstream-source"]}

    await ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME)

    await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", timeout=1000)


@pytest.mark.abort_on_fail
async def test_given_tls_provider_when_integrate_then_status_is_active(ops_test: OpsTest):
    assert ops_test.model

    await ops_test.model.deploy(
        TLS_PROVIDER_CHARM_NAME,
        application_name=TLS_PROVIDER_CHARM_NAME,
        channel=TLS_PROVIDER_CHARM_CHANNEL,
    )

    await ops_test.model.integrate(relation1=APP_NAME, relation2=TLS_PROVIDER_CHARM_NAME)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        timeout=1000,
    )
