# ******************************************************************************
# Copyright (c) 2020-2023, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
# -*- coding: utf-8 -*-
import re
import time
from datetime import datetime, timedelta

from connect import resources
from connect.config import Config
from connect.models import UsageRecord

from cloudblue_connector_backend.connector import ConnectorMixin
from cloudblue_connector_backend.consumption.base import Zero

from cloudblue_connector.automation.usage_file import UsageFileAutomation
from connect.rql import Query



class UsageAutomation(resources.UsageAutomation, ConnectorMixin):
    """Automates reporting of Usage Files"""

    usages = []

    def _format_usage_record_id(self, subscription_id, report_time, mpn):
        return "{}-{}-{}".format(subscription_id, report_time.isoformat(), mpn)

    def process_request(self, request):
        """Generate UsageFile for each active Asset"""

        # store each processed request for debug
        self.usages.append(request)

        if self.test_marketplace_requests_filter(Config.get_instance(), request.id, request.marketplace):
            return

        subscription_id = request.id
        if not self.is_resource_exist(subscription_id):
            self.logger.warning("Can't find resources for subscription {} on backend".format(subscription_id))
            return

        params = {p.id: p for p in request.params}
        start_check_from = None
        if 'resume_date' in params:
            resume_date = params.get('resume_date')
            if resume_date.value:
                start_check_from = datetime.strptime(resume_date.value, '%Y-%m-%d %H:%M:%S')

        name_format = '{asset}_{date}'
        description_format = 'Report for {asset} {date}'
        current_date = datetime.utcnow()
        search_criteria = name_format.format(asset=subscription_id, date=current_date.strftime('%Y-%m-*'))

        usage_files = UsageFileAutomation()
        filters = Query().like('name', search_criteria)
        if self.config.products:
            filters.in_('product_id', self.config.products)
        found = usage_files.list(filters)
        found = [f for f in found or [] if f.status != 'deleted' and f.status != 'draft']

        current_report_name = None
        if found:
            found = sorted(found, key=lambda rep: time.mktime(rep.events.uploaded.at.timetuple()))
            report = found[-1]

            if report.status == 'accepted':
                current_report_name = report.name
                rex = r"\s+(?=\d{2}(?:\d{2})?-\d{1,2}-\d{1,2}\b)"
                report_time = re.split(rex, report.description)[-1]
                report_time = datetime.strptime(report_time, '%Y-%m-%d %H:%M:%S')
                start_report_time = report_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                end_report_time = start_report_time + timedelta(hours=1)
                if not self.is_report_suspended_needed() and start_check_from and start_check_from > start_report_time:
                    self.logger.info("start_check_from: {} > start_report_time {}, looks like subscription was "
                                     "resumed after suspend, skipping this perood and start"
                                     "reporting from now".format(start_check_from, start_report_time))
                    start_report_time = start_check_from.replace(minute=0, second=0, microsecond=0)
                    end_report_time = start_report_time + timedelta(hours=1)
                    if current_date - end_report_time < timedelta(hours=0):
                        self.logger.error("%s: skip process while current report period is not ended", request.id)
                        return
            elif report.status in ('processing', 'draft', 'uploading', 'ready'):
                self.logger.info("%s: usage report '%s' is being processed", request.id, report.name)
                return
            elif report.status in ('invalid', 'rejected'):
                # we have to wait when user remove invalid report
                self.logger.error("%s: failed usage report '%s' found", request.id, report.name)
                return
            else:
                self.logger.error("%s: unknown status of usage report '%s' found", request.id, report.name)
                return
        else:
            end_report_time = current_date.replace(minute=0, second=0, microsecond=0)
            start_report_time = end_report_time - timedelta(hours=1)

        if end_report_time > current_date:
            self.logger.error("%s: skip process while current report period is not ended", request.id)
            return

        report_name = name_format.format(asset=request.id, date=start_report_time.strftime('%Y-%m-%d_%Hh'))
        report_description = description_format.format(asset=request.id,
                                                       date=start_report_time.strftime('%Y-%m-%d %H:%M:%S'))

        if current_report_name and current_report_name == report_name:
            self.logger.info("%s: usage report '%s' for current period already provided, skipping...", request.id,
                             report_name)
            return

        usage_file = self.create_usage_file(
            report_name,
            report_description,
            request,
            start_report_time,
            end_report_time
        )

        # report for each hour since last report date
        self.logger.info("%s-%s: creating report from %s to %s", request.id, subscription_id, start_report_time,
                         end_report_time)
        items = {item.mpn: item for item in request.items}
        usage_records = self.collect_usage_records(items, subscription_id, start_report_time, end_report_time)
        if usage_records:
            self.submit_usage(usage_file=usage_file, usage_records=usage_records)

    def collect_usage_records(self, items, subscription_id, start_time, end_time):
        """Create UsageRecord object for each type of resources"""
        consumptions = self.consumptions
        conf = Config.get_instance()

        consumptions.update({mpn: Zero() for mpn in conf.misc.get('report_zero_usage', [])})

        def known_resources(item):
            return item in consumptions

        def collect_item_consumption(item):
            return self.create_record(
                subscription_id, start_time, end_time, item,
                consumptions.get(item).collect_consumption(subscription_id, start_time, end_time))

        return map(collect_item_consumption, filter(known_resources, items))

    def create_record(self, subscription_id, start_time, end_time, mpn, value):
        """Create UsageRecord object"""

        self.logger.info("add '%s' value %s", mpn, value)
        return UsageRecord(
            usage_record_id=self._format_usage_record_id(subscription_id, end_time, mpn),
            item_search_criteria='item.mpn',
            item_search_value=mpn,
            amount=value,
            quantity=value,
            start_time_utc=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_time_utc=end_time.strftime('%Y-%m-%d %H:%M:%S'),
            asset_search_criteria=self.usage_record_search_criteria,
            asset_search_value=subscription_id,
        )

    # Listing in not available for TestMarket, we implement
    # our own version of Asset listing using Directory API
    # to have same code for TaskMarket and production
    def list(self, filters=None):
        """List all active Assets"""
        from connect.resources.directory import Directory
        filters = filters or self.filters()
        assets = list(Directory().list_assets(filters=filters))

        for a in assets:
            # contract's marketplace is emtpy
            # let's use from asset
            a.contract.marketplace = a.marketplace
            # provider is used in debug logs
            a.provider = a.connection.provider

        return assets
