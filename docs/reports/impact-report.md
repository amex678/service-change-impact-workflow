# Service-change impact report

> SYNTHETIC SAMPLE inputs are explicitly marked below; do not treat them as real-environment evidence.
> AI-assisted evidence review is not human approval. Nothing was merged or deployed.

## 1. Scope and completeness

| Item | Value |
|---|---|
| Input snapshot | 2026-10-10T01:16:54Z |
| Run | https://github.com/amex678/service-change-impact-workflow/actions/runs/38012531004 |
| Azure Updates | 211 notices; complete; recent since 2026-09-26T01:16:52Z plus active retirements |
| Azure inventory | sample subscription (synthetic); captured 2026-10-01T00:00:00Z; 10/12 resources mapped; SYNTHETIC SAMPLE |
| Microsoft 365 | included; 4 notices; notices=sample; profile=sample; profile captured 2026-10-01T00:00:00Z |
| Evaluated | 12/12 candidates |
| Deferred / already tracked | 41 / 0 |
| Out of matching scope | 161 Azure; 1 Microsoft 365 (not evaluated, not 'not impacted') |

> Warning: Some inventory resource types are not mapped to Azure Updates products and were not evaluated.

> Warning: Some candidates exceeded the per-run limit and were not evaluated in this run.

> Warning: The Azure inventory is a synthetic sample, not a real environment.

> Warning: The Microsoft 365 notices and tenant profile are synthetic samples.

## 2. Verdicts

| Notice | Change and effective date | Matched resources or settings / checked scope | Deciding evidence | Verdict | Next step |
|---|---|---|---|---|---|
| [Azure 500157: Retirement: Operating System (OS) Disks on Standard HDD will be retired on 08 September 2028](https://azure.microsoft.com/updates?id=500157) | 2028-09-08 | `disks-01`; disk roles reviewed individually | `disks-01` has `sku.name=Standard_LRS` and `osType=Windows`, matching an HDD OS disk. `disks-02` has no captured OS role; `disks-03` is Premium. | Impacted | Keep Issue 7; migrate the confirmed OS disk after approval. Investigate `disks-02`; do not classify every HDD disk as affected. |
| [Azure 572770: Retirement: Support for PowerShell 7.4 ends on November 10, 2026](https://azure.microsoft.com/updates?id=572770) | 2026-11-10 | `sites-01`; Windows Function App | `powerShellVersion=7.4` matches the retiring runtime. `reserved=false` and the Windows Consumption template do not meet the Linux Consumption prerequisite for Flex migration. | Impacted | Keep Issue 4 and draft PR 9. CI passed; runtime/module smoke tests remain required before any approved deployment. |
| [Azure 557852: Retirement:  TLS 1.0 and TLS 1.1 in Azure App Service, Azure Functions, and Azure Logic Apps](https://azure.microsoft.com/updates?id=557852) | 2027-05-31 | Application endpoint confirmed; SCM and clients not captured | `minTlsVersion=1.2` excludes legacy TLS on the application endpoint. The independent SCM minimum and client compatibility were not captured, so a whole-notice no-impact claim is not justified. | Needs investigation | Read `scmMinTlsVersion` and test the relevant application/deployment clients; preserve the confirmed application-endpoint exclusion. |
| [M365 MC-SAMPLE-001: [SAMPLE] Authentication methods: SMS sign-in will require a policy update](https://github.com/amex678/service-change-impact-workflow/blob/main/data/samples/m365-message-center.sample.json) | 2026-12-01 (fictional sample) | SMS authentication policy; primary sign-in flag absent | SMS is enabled for all users, but the profile omits `includeTargets[].isUsableForSignIn`. Enabled authentication is not proof of enabled SMS primary sign-in. | Needs investigation | Correct Issue 5 from Impacted to Needs investigation. Read the sign-in target flag and intended users; do not change the tenant. |
| [Azure 493779: Retirement: Azure Disk Encryption](https://azure.microsoft.com/updates?id=493779) | 2028-09-15 | `virtualmachines-01`; ADE state absent | The VM inventory contains OS/size/disk facts but no ADE extension or guest encryption state. A Disk Encryption Set describes SSE/CMK and does not prove ADE use. | Needs investigation | Keep Issue 8; inspect ADE extensions and encryption state, not DES presence alone. |
| [Azure 551523: Retirement: "Send data to Event Hubs & Storage (Preview)" retiring July 31, 2026](https://azure.microsoft.com/updates?id=551523) | 2026-07-31 | Azure Monitor resources; DCR feature settings not captured | The notice targets a specific preview export capability, not AMA generally. The inventory lacks DCR/export destination configuration proving whether this capability is used. | Needs investigation | Check DCR destinations and VM-client data export settings; if enabled, review a supported replacement. The deadline has passed, but observed data loss is not established. |
| [Azure 560948: Retirement: Azure Reserved Virtual Machines Instances for select VM series](https://azure.microsoft.com/updates?id=560948) | 2026-07-01 | Captured VM series excluded; reservation orders not captured | `virtualmachines-01` is `Standard_D2s_v5`, outside the listed retiring series. The notice concerns reservation purchases/renewals; current VM size does not exclude affected orders elsewhere in the account. | Needs investigation | Review reservation orders, renewals and expirations in Issue 11. Preserve the captured VM-series exclusion without claiming account-wide absence of impact. |
| [Azure 498749: Retirement: Microsoft Defender for Cloud Deprecation in Microsoft Azure Operated by 21Vianet Announcement](https://azure.microsoft.com/updates?id=498749) | 2026-08-18 | Subscription-level cloud context not explicitly captured | The notice is limited to Azure operated by 21Vianet. Captured resources are in Japan East, but no explicit subscription cloud identifier was recorded; do not turn that gap into a global no-impact conclusion. | Needs investigation | Confirm the subscription cloud. If AzureCloud, exclude this China-only notice; if AzureChinaCloud, assess the retired features. |
| [Azure azure-monitor-data-collection-api-retirement: Azure Monitor Data Collection API Retirement](https://azure.microsoft.com/updates?id=azure-monitor-data-collection-api-retirement) | 2026-09-14 | `workspaces-01`, `components-01`; external senders excluded from capture | Workspace/component existence does not prove use of the legacy Data Collector API. The inventory has no sender endpoint, shared-key ingestion or DCR-based ingestion usage evidence. | Needs investigation | Keep Issue 2; inspect sender code/configuration and ingestion telemetry. Do not claim an outage or completed migration. |
| [Azure 559311: Retirement: Azure Functions runtime v3 on Linux Consumption will stop running September 30, 2026](https://azure.microsoft.com/updates?id=559311) | 2026-09-30 | Captured Windows Function App and declared template | This enforcement requires both Linux Consumption and runtime v3. `reserved=false` identifies the captured Windows plan, and the template declares `FUNCTIONS_EXTENSION_VERSION=~4`; the required Linux/v3 combination is excluded. | Not impacted | No action for this captured app; do not generalize the result to apps outside this inventory. |
| [Azure 501673: Retirement: Azure Monitor SCOM Managed Instance will be retired on Sep 30, 2026](https://azure.microsoft.com/updates?id=501673) | 2026-09-30 | The 12-resource synthetic inventory and declared IaC only | The notice concerns SCOM Managed Instance, not all Azure Monitor resources. The captured resources include Application Insights/Log Analytics but no SCOM MI resource or declaration. | Not impacted | No action for the captured sample resources. A real assessment must include SCOM MI inventory before extending this conclusion. |
| [M365 MC-SAMPLE-002: [SAMPLE] Exchange Online: a legacy mailbox access protocol will be turned off](https://github.com/amex678/service-change-impact-workflow/blob/main/data/samples/m365-message-center.sample.json) | No deadline stated in the fictional notice | Exchange Online settings; protocol usage absent | Exchange is in use, but the profile contains no mailbox/client protocol usage. The deciding usage fact is missing; neither impact nor absence of impact is established. | Needs investigation | Keep Issue 6; obtain a sanitized protocol-usage report. Do not invent a cutoff date or change the tenant. |

## 3. Details for Impacted and Needs investigation

This is an AI-assisted evidence review of [live run 38012531004](https://github.com/amex678/service-change-impact-workflow/actions/runs/38012531004), all 12 delivered candidate rows, the original six finding Issues and four new investigation Issues. The run delivered Markdown, HTML and metadata, and the mandatory `verify-report` job passed. The original October 6 artifact was missing; this does not claim to recover that unpublished report. Inventory/profile facts remain the 2026-10-01 synthetic snapshot, not live environment observations.

This final review yields **2 Impacted, 2 Not impacted (explicitly limited scope), 8 Needs investigation, 0 Cannot evaluate**. All notices were readable; incomplete configuration is reported as Needs investigation rather than silently treated as no impact.

The original agent's completion log listed the same 12 candidate keys: 3 Impacted, 3 Needs investigation and 6 Not impacted. Five verdicts change: `MC-SAMPLE-001` changes from Impacted to Needs investigation; Azure `557852`, `551523`, `560948` and `498749` change from Not impacted to Needs investigation because SCM/client, preview-export, reservation-order and subscription-cloud facts were not captured. The remaining seven verdicts are retained with explicit scope and missing facts.

The delivered raw run incorrectly called `disks-02` a data disk in its table despite missing role evidence; this reviewed report corrects that assertion. Its broader reservation-investigation verdict is retained: excluding the captured v5 VM is not an account-wide reservation review. Shape/delivery validation is not a substitute for factual review. New investigation findings are [Issue 10](https://github.com/amex678/service-change-impact-workflow/issues/10), [Issue 11](https://github.com/amex678/service-change-impact-workflow/issues/11), [Issue 12](https://github.com/amex678/service-change-impact-workflow/issues/12) and [Issue 13](https://github.com/amex678/service-change-impact-workflow/issues/13). No duplicate original finding or new PR was created.

### Azure 500157: Standard HDD OS disks

- **Source:** https://azure.microsoft.com/updates?id=500157
- **Confirmed:** the retirement is for Standard HDD OS disks; Standard HDD data disks are explicitly excluded.
- **Correction:** Issue 7 must separate confirmed `disks-01` from the unclassified `disks-02`. Missing `osType` is not proof that a disk is a data disk.
- **Next step:** a human chooses disk type, workload validation and migration window. No disk was converted.

### Azure 572770: PowerShell 7.4

- **Source:** https://azure.microsoft.com/updates?id=572770
- **Confirmed:** support ends 2026-11-10; the recommended target is 7.6. The Linux Consumption prerequisite does not apply to the captured Windows app.
- **Correction:** Issue 4 had literal newline escapes and a redacted source link; replace them with proper Markdown and the original URL.
- **PR validation:** draft PR 9 changes only the runtime parameter. Unit tests, Bicep build, actionlint and offline infrastructure validation passed on the PR commit. No merge, what-if against Azure, deployment or function smoke test was performed.

### Azure 557852: TLS 1.0 / 1.1

- **Source:** https://azure.microsoft.com/updates?id=557852
- **Supporting documentation:** [App Service TLS settings](https://learn.microsoft.com/en-us/azure/app-service/overview-tls).
- **Confirmed:** the application endpoint already requires TLS 1.2. SCM TLS can be configured independently; its value and client compatibility are absent.
- **Next step:** capture those facts. Do not assume a documented default equals observed configuration.

### M365 MC-SAMPLE-001: SMS sign-in

- **Source:** fictional sample `MC-SAMPLE-001`; this is not a Microsoft announcement.
- **Supporting documentation:** [Microsoft Graph SMS target](https://learn.microsoft.com/en-us/graph/api/resources/smsauthenticationmethodtarget?view=graph-rest-1.0).
- **Correction:** the original Impacted verdict overstates the captured evidence. `isUsableForSignIn` determines primary sign-in and is not included in the profile.
- **Next step:** obtain the target sign-in flag before deciding impact. No M365 configuration change is authorized.

### Azure 493779: Azure Disk Encryption

- **Source:** https://azure.microsoft.com/updates?id=493779
- **Supporting documentation:** [Managed disk encryption options](https://learn.microsoft.com/en-us/azure/virtual-machines/disk-encryption-overview).
- **Confirmed:** ADE retires 2028-09-15; the notice warns about unlocking after reboots, not an observed outage in this sample.
- **Correction:** a Disk Encryption Set or SSE/CMK configuration is not an equivalent ADE detection signal. Issue 8 remains Needs investigation, with the check narrowed to ADE-specific evidence.
- **Next step:** verify ADE extensions/guest encryption and, only if enabled, review Encryption at Host or another supported migration.

### Azure 551523: VM client data preview export

- **Source:** https://azure.microsoft.com/updates?id=551523
- **Confirmed:** the retired capability is the VM-client data export preview; AMA generally remains supported.
- **Gap:** DCR/export settings and actual sender usage are not captured. Azure Monitor presence alone does not prove use.
- **Next step:** capture the specific preview configuration and destinations. The date is past; no data-loss claim is made.

### Azure 498749: Defender for Cloud in 21Vianet

- **Source:** https://azure.microsoft.com/updates?id=498749
- **Confirmed:** the retirement is limited to the 21Vianet environment, effective 2026-08-18.
- **Gap:** the inventory has region values but no explicit cloud identifier. This subscription-wide match cannot be settled from an assumed cloud.
- **Next step:** record the cloud and then exclude or assess the notice. No Defender setting was changed.

### Azure 560948: Select VM-series reservations

- **Source:** https://azure.microsoft.com/updates?id=560948
- **Confirmed:** selected-series RI purchases/renewals are retired from 2026-07-01; existing reservations continue through their term.
- **Scope:** `Standard_D2s_v5` is not a named retiring VM series. Reservation orders, renewals and expirations are not captured; this does not exclude account-wide reservation impact.
- **Next step:** keep Issue 11 as Needs investigation and obtain reservation-order evidence. Do not infer a price increase, affected order or elapsed reservation from the current VM size.

### Azure azure-monitor-data-collection-api-retirement: Data Collector API

- **Source:** https://azure.microsoft.com/updates?id=azure-monitor-data-collection-api-retirement
- **Confirmed:** the legacy Data Collector API retired 2026-09-14; DCR-based Log Ingestion is the replacement.
- **Gap:** neither sender implementation nor ingestion usage was captured. `IngestionMode=LogAnalytics` on Application Insights does not settle unrelated custom log sender behavior.
- **Next step:** review endpoints, authentication and ingestion telemetry. Keep Issue 2 as Needs investigation.

### M365 MC-SAMPLE-002: Legacy Exchange protocol

- **Source:** fictional sample `MC-SAMPLE-002`; this is not a Microsoft announcement.
- **Confirmed:** impact requires actual legacy protocol usage, which is absent from the tenant profile.
- **Deadline:** the fictional notice provides none. No date is inferred from publication or modification timestamps.
- **Next step:** obtain protocol-usage evidence. Keep Issue 6 as Needs investigation.

## 4. Not evaluated in this run

| Notice | Reason |
|---|---|
| Azure 500853: Retirement: Legacy Authentication in Azure Monitor - Container Insights will be retired on September 30, 2026. | over the per-run limit of 10 azure candidates |
| Azure 573414: Retirement: NVv3-series Azure Virtual Machines | over the per-run limit of 10 azure candidates |
| Azure 573415: Retirement: NVv4-series Azure Virtual Machines | over the per-run limit of 10 azure candidates |
| Azure 568661: Retirement: Nested confidential (cc_v5) VMs will be retired on September 1, 2026 | over the per-run limit of 10 azure candidates |
| Azure transition-to-azure-ad-to-query-data-from-azure-monitor-application-insights-by-31-march-2026: Retirement: Transition to Entra ID (formerly known as Azure AD) to query data from Azure Monitor application insights by September 30, 2026 | over the per-run limit of 10 azure candidates |
| Azure 498563: Retirement: Upgrade BlobFuse v1 to latest version of Blobfuse v2 | over the per-run limit of 10 azure candidates |
| Azure support-for-the-1x-version-of-azure-functions-ends-14-september-2026: Support for the 1.x version of Azure Functions ends 14 September 2026 | over the per-run limit of 10 azure candidates |
| Azure transition-to-the-containerlogv2-table-by-30-september-2026: Transition to the ContainerLogV2 table by 30 September 2026 | over the per-run limit of 10 azure candidates |
| Azure 513892: Retirement: Deprecation of Custom Resource Providers | over the per-run limit of 10 azure candidates |
| Azure 564441: Retirement: GPv1 and Legacy Blob storage account creation | over the per-run limit of 10 azure candidates |
| Azure 496964: Retirement: General Purpose v1 (GPv1) and legacy blob storage accounts | over the per-run limit of 10 azure candidates |
| Azure 545771: Retirement: Support for Python 3.10 ends on October 1, 2026 – upgrade your Azure Functions apps to Python 3.13 | over the per-run limit of 10 azure candidates |
| Azure 509686: Retirement: Support for Python 3.10 ends on October 1st, 2026 | over the per-run limit of 10 azure candidates |
| Azure 558033: Retirement: Support for .NET 8 (LTS) ends on November 10, 2026—upgrade your apps to .NET 10 (LTS) | over the per-run limit of 10 azure candidates |
| Azure 572838: Retirement: Support for .NET 8 and .NET 9 ends on November 10, 2026—upgrade your apps to .NET 10 | over the per-run limit of 10 azure candidates |
| Azure 485077: Retirement: Support for .NET 9 (STS) ends on November 10, 2026 | over the per-run limit of 10 azure candidates |
| Azure retirement-support-for-the-inprocess-model-for-net-apps-in-azure-functions-ends-10-november-2026: Retirement: Support for the in-process model for .NET apps in Azure Functions ends 10 November 2026. | over the per-run limit of 10 azure candidates |
| Azure php-82-app-svc: Retirement: Extended support for PHP 8.2 ends December 31st, 2026 – upgrade apps to PHP 8.3 | over the per-run limit of 10 azure candidates |
| Azure 558276: Retirement: AzureDnsEndpoints for Azure storage accounts will be retired March 2027 | over the per-run limit of 10 azure candidates |
| Azure 550519: Retirement: Deprecation of sidecar for remote-write for Azure Monitor managed service for Prometheus | over the per-run limit of 10 azure candidates |
| Azure 558027: Retirement: Python support for Azure App Service and Azure Functions on Windows will be retired on March 31, 2027 | over the per-run limit of 10 azure candidates |
| Azure 567334: Retirement: Support for Node 22 LTS ends on April 30, 2027 | over the per-run limit of 10 azure candidates |
| Azure 572771: Retirement: Support for Node.js 22 ends on April 30, 2027 | over the per-run limit of 10 azure candidates |
| Azure 548525: Retirement: HBv2-series Azure Virtual Machines will be retired on May 31, 2027 | over the per-run limit of 10 azure candidates |
| Azure 548543: Retirement: HC-series Azure Virtual Machines will be retired on May 31, 2027 | over the per-run limit of 10 azure candidates |
| Azure 548497: Retirement: NP-series Azure Virtual Machines will be retired on May 31, 2027 | over the per-run limit of 10 azure candidates |
| Azure 568585: Retirement: Support for Java 8, 11 and 17 will end on September 1, 2027 | over the per-run limit of 10 azure candidates |
| Azure 485047: Retirement: Azure App Service Will No Longer Support Linked Databases as a Part of Custom Backups After March 31, 2028 | over the per-run limit of 10 azure candidates |
| Azure 489009: Retirement: Azure Functions – Durable Functions support for Netherite will end on March 31, 2028 | over the per-run limit of 10 azure candidates |
| Azure 486080: Retirement: Log Analytics Batch API to Be Retired on March 31, 2028 | over the per-run limit of 10 azure candidates |
| Azure 485569: Retirement: D, Ds, Dv2, Dsv2, and Ls Series Virtual Machines to Be Retired on May 1, 2028 | over the per-run limit of 10 azure candidates |
| Azure 491629: Retirement: VM Insights Map and Dependency Agent are being on June 30, 2028 | over the per-run limit of 10 azure candidates |
| Azure 499451: Retirement: The Linux Consumption hosting plan of Azure Functions will be retired on September 30, 2028. Migrate to Flex Consumption. | over the per-run limit of 10 azure candidates |
| Azure transition-to-using-standard-tests-for-singlestep-availability-testing-in-azure-monitor-application-insights-by-30-september: Retirement: Transition to using standard tests for single-step availability testing in Azure Monitor application insights by September 30, 2028 | over the per-run limit of 10 azure candidates |
| Azure 494676: Retirement: hsmPlatform 1 Keys in Azure Key Vault | over the per-run limit of 10 azure candidates |
| Azure 568178: Retirement: Azure App Service on Azure Stack Hub | over the per-run limit of 10 azure candidates |
| Azure 569592: Retirement: DCsv3 and DCdsv3-series Azure Virtual Machines will be retired on October 31, 2029 | over the per-run limit of 10 azure candidates |
| Azure 572346: Retirement: Dv3, Dsv3, Ev3, and Esv3 Azure VMs | over the per-run limit of 10 azure candidates |
| Azure 572630: Generally Available: Storage optimized Lasv5 and Laosv5 Azure VM series | over the per-run limit of 10 azure candidates |
| M365 MC-SAMPLE-003: [SAMPLE] Microsoft Teams: updated layout for meeting recap | informational (stay informed) |
| Azure 571075: Public Preview: Automatic Zone Placement for Virtual Machine Scale Sets | informational (feature, preview, region or service update) |

## 5. Coverage gaps

- Unmapped resource types: microsoft.purview/accounts (1)
- Ignored resource types: microsoft.managedidentity/userassignedidentities (1)

## 6. Reviewer checklist

- [x] Every selected candidate has exactly one valid verdict and deciding evidence (automated validation).
- [ ] A human owner accepts or corrects the evidence and the stated scope.
- [ ] Missing usage, cloud, client or policy settings have been obtained where needed.
- [ ] Owners and dates are assigned to findings before action.
- [ ] Any draft pull request passes checks and receives human approval before deployment.
