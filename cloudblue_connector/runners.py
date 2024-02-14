# ******************************************************************************
# Copyright (c) 2020-2023, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
# -*- coding: utf-8 -*-
import warnings

from cloudblue_connector.automation import FulfillmentAutomation, UsageAutomation, UsageFileAutomation
from cloudblue_connector_backend.connector import ConnectorConfig
from connect.rql import Query

from cloudblue_connector.core import ConnectorPasswords

# Enable processing of deprecation warnings
warnings.simplefilter('default')


def process_fulfillment():
    """Process all new Fulfillments"""
    ConnectorConfig(file='/etc/cloudblue-connector/config.json', report_usage=False)
    mngr = FulfillmentAutomation()
    if not mngr.is_backend_alive():
        return
    mngr.process()
    return mngr.fulfillments


def process_usage():
    """Confirm all created UsageFiles"""

    ConnectorConfig(file='/etc/cloudblue-connector/config.json', report_usage=True)
    mngr = UsageAutomation()
    if not mngr.is_backend_alive():
        return
    if mngr.is_report_suspended_needed():
        filters = Query().in_('status', ['active', 'suspended'])
    else:
        filters = Query().in_('status', ['active'])
    mngr.process(filters)
    return mngr.usages

def process_usage_files():
    """Confirm all created UsageFiles"""

    ConnectorConfig(file='/etc/cloudblue-connector/config.json', report_usage=True)
    mngr = UsageFileAutomation()
    if not mngr.is_backend_alive():
        return
    mngr.process()
    return mngr.files


def set_cloudblue_token(token):
    mngr = ConnectorPasswords()
    result = mngr.set_service_password('cloudblue', token)
    if isinstance(result, int):
        return True
    return False


def set_pp_password(token):
    mngr = ConnectorPasswords()
    result = mngr.set_service_password('power_panel', token)
    if isinstance(result, int):
        return True
    return False


def set_onnap_token(token):
    mngr = ConnectorPasswords()
    result = mngr.set_service_password('onnap', token)
    if isinstance(result, int):
        return True
    return False
