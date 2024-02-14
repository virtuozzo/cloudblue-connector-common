# ******************************************************************************
# Copyright (c) 2020-2023, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
# -*- coding: utf-8 -*-

from connect import resources
from connect.config import Config
from connect.exceptions import SkipRequest
from cloudblue_connector_backend.connector import ConnectorMixin
from cloudblue_connector.core.logger import context_log


class FulfillmentAutomation(resources.FulfillmentAutomation, ConnectorMixin):
    """This is the automation engine for Fulfillments processing"""

    fulfillments = []

    @context_log
    def process_request(self, request):
        """Each new Fulfillment is processed by this function"""

        conf = Config.get_instance()

        # store all processed request for debug
        self.fulfillments.append(request)

        if request.needs_migration():
            # Skip request if it needs migration
            # (migration is performed by an external service)
            self.logger.info('Skipping request %s because it needs migration.', request.id)
            raise SkipRequest()

        if self.test_marketplace_requests_filter(conf, request.id, request.asset.marketplace):
            raise SkipRequest()

        rv, params_update = self.process_fulfillment_request(request)
        if params_update:
            self.update_parameters(request.id, params_update)
        return rv
