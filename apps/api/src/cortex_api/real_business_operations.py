"""Source-grounded operations from the Drive business playbooks.

Lead review, paid-media arithmetic, weekly operations review and pilot economics.
Draft-only: no external messages, CRM changes, ad changes or invented metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any


def timestamp(value: str | float | None) -> float | None:
    if value is None or value=='':
        return None
    if isinstance(value,(int,float)):
        if not math.isfinite(value):
            raise ValueError('nonfinite timestamp')
        return float(value)
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required for source timestamps')
    return parsed.timestamp()


@dataclass
class LeadReview:
    record_id: str
    name: str
    classification: str
    reason: str
    draft: str
    next_action: str
    source: str
    warnings: list[str] = field(default_factory=list)


class BusinessOperationsEngine:
    def review_leads(self, records: list[dict], now: float, overdue_days: int = 5,
                     lookback_days: int = 14, reporting_timezone: str = 'UTC') -> dict:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(reporting_timezone)
        if not 1<=overdue_days<=365 or not 1<=lookback_days<=365 or not math.isfinite(now):
            raise ValueError('invalid lead review window')
        reviewed,excluded,duplicates = [],[],[]
        seen: dict[str,str] = {}
        from dataclasses import asdict
        for record in records:
            identifier = str(record.get('id',''))
            if record.get('opted_out') or record.get('do_not_contact'):
                excluded.append({'id':identifier,'reason':'opted_out'})
                continue
            contact = str(record.get('email') or record.get('phone') or identifier).strip().lower()
            if contact and contact in seen:
                duplicates.append({'id':identifier,'duplicate_of':seen[contact]})
                continue
            if contact:
                seen[contact] = identifier
            updated = timestamp(record.get('updated_at') or record.get('added_at'))
            last = timestamp(record.get('last_interaction'))
            if updated is not None and now-updated>lookback_days*86400 and (last is None or now-last<overdue_days*86400):
                continue
            name,source = str(record.get('name','')),str(record.get('source',''))
            missing = [key for key in ('id','name','source','owner','status') if not record.get(key)]
            if updated is not None and updated>now or last is not None and last>now:
                missing.append('future_timestamp')
            status = str(record.get('status','')).lower()
            age = (now-last)/86400 if last is not None else None
            if missing:
                classification,reason = 'Unclear','Missing or invalid source fields'
            elif status in {'won','customer','closed_won'}:
                classification,reason = 'Won','Source marks this lead won'
            elif status in {'not_fit','not a fit','lost','disqualified'}:
                classification,reason = 'Not a fit','Source marks this lead not a fit'
            elif last is not None and datetime.fromtimestamp(last,zone).date()==datetime.fromtimestamp(now,zone).date():
                classification,reason = 'Waiting on customer','Already contacted today ('+reporting_timezone+')'
            elif status in {'waiting','waiting_on_customer'} and age is not None and age<overdue_days:
                classification,reason = 'Waiting on customer','Awaiting customer within follow-up window'
            elif age is not None and age>=overdue_days:
                classification,reason = 'Needs follow-up',f'No interaction for {int(age)} days'
            elif last is None and status in {'new','open'}:
                classification,reason = 'New','No interaction recorded'
            else:
                classification,reason = 'Unclear','Source does not establish next action'
            draft = ''
            if classification in {'New','Needs follow-up'}:
                interest = str(record.get('interest','')).strip()
                if interest:
                    draft = f'Hi {name}, following up on your interest in {interest}. Would you like to discuss the next step?'
                else:
                    missing.append('interest')
            reviewed.append(asdict(LeadReview(identifier,name,classification,reason,draft,
                'Review draft before sending' if draft else 'Verify source record',source,missing)))
        return {'leads':reviewed,'excluded':excluded,'duplicates':duplicates,'mode':'draft_only','as_of':now}

    @staticmethod
    def _metrics(records: list[dict]) -> dict:
        fields = ('spend','impressions','clicks','leads','purchases','revenue')
        totals = {}
        for key in fields:
            values = [r.get(key) for r in records]
            if any(value is not None and (not isinstance(value,(int,float)) or not math.isfinite(value) or value<0) for value in values):
                raise ValueError('nonnegative finite ad metrics required')
            totals[key] = sum(values) if values and all(v is not None for v in values) else None
        def ratio(a: str,b: str,scale: float = 1) -> float | None:
            return totals[a]/totals[b]*scale if totals[a] is not None and totals[b] is not None and totals[b]>0 else None
        return {**totals,'ctr_pct':ratio('clicks','impressions',100),'cpc':ratio('spend','clicks'),
                'cpl':ratio('spend','leads'),'cpa':ratio('spend','purchases'),'roas':ratio('revenue','spend')}

    def ad_report(self, rows: list[dict], date: str, reporting_timezone: str,
                  attribution_window: str, previous: list[dict] | None = None,
                  trailing: list[dict] | None = None, budget: float | None = None,
                  spend_change_threshold: float = 0.25, cpl_change_threshold: float = 0.2) -> dict:
        from zoneinfo import ZoneInfo
        ZoneInfo(reporting_timezone)
        datetime.strptime(date,'%Y-%m-%d')
        if budget is not None and (not math.isfinite(budget) or budget<0):
            raise ValueError('invalid budget')
        if not attribution_window:
            raise ValueError('attribution window required')
        valid,failures = [],[]
        currencies = {r.get('currency') for r in rows if r.get('currency')}
        if len(currencies)>1:
            raise ValueError('mixed currencies cannot be summed without explicit FX conversion')
        seen = set()
        for row in rows:
            identity = (row.get('source'),row.get('campaign'),row.get('date'),row.get('account'))
            if identity in seen:
                failures.append({'source':row.get('source'),'reason':'duplicate source row'})
                continue
            seen.add(identity)
            if row.get('date')!=date or row.get('timezone')!=reporting_timezone or row.get('attribution_window')!=attribution_window:
                failures.append({'source':row.get('source'),'reason':'incomparable reporting window'})
            elif not row.get('source') or not row.get('campaign'):
                failures.append({'source':row.get('source'),'reason':'missing provenance'})
            elif row.get('error'):
                failures.append({'source':row['source'],'reason':'source unavailable'})
            else:
                valid.append(row)
        totals = self._metrics(valid)
        campaigns = []
        for name in dict.fromkeys(row['campaign'] for row in valid):
            group = [row for row in valid if row['campaign']==name]
            campaigns.append({'campaign':name,**self._metrics(group),'sources':list(dict.fromkeys(row['source'] for row in group))})
        comparable_previous = [r for r in (previous or []) if r.get('timezone')==reporting_timezone and r.get('attribution_window')==attribution_window and r.get('source') and not r.get('error') and r.get('date')==str(datetime.fromisoformat(date).date()-__import__('datetime').timedelta(days=1))]
        prev = self._metrics(comparable_previous)
        changes = {key:(totals[key]/prev[key]-1) if totals.get(key) is not None and prev.get(key) is not None and prev[key]>0 else None for key in ('spend','cpl','roas')}
        trailing_days = {}
        target_date = datetime.fromisoformat(date).date()
        for row in trailing or []:
            day = datetime.fromisoformat(row['date']).date()
            if 1<=(target_date-day).days<=7 and row.get('timezone')==reporting_timezone and row.get('attribution_window')==attribution_window and row.get('source') and not row.get('error'):
                trailing_days.setdefault(row['date'],[]).append(row)
        trailing_totals = [self._metrics(group) for group in trailing_days.values()]
        averages = {key:sum(r[key] for r in trailing_totals)/len(trailing_totals) if trailing_totals and all(r[key] is not None for r in trailing_totals) else None for key in ('spend','leads','purchases','revenue')}
        flags = []
        if changes['spend'] is not None and abs(changes['spend'])>spend_change_threshold:
            flags.append('Material spend change versus previous day')
        if changes['cpl'] is not None and changes['cpl']>cpl_change_threshold:
            flags.append('Cost per lead increased beyond threshold')
        if budget is not None and totals['spend'] is not None and totals['spend']>budget:
            flags.append('Spend exceeds stated budget')
        return {'date':date,'timezone':reporting_timezone,'attribution_window':attribution_window,'totals':totals,'campaigns':campaigns,
                'previous_day_change':changes,'trailing_daily_average':averages,'trailing_days_available':len(trailing_days),
                'flags':flags,'source_failures':failures,'freshness':[{'source':r['source'],'updated_at':r.get('updated_at')} for r in valid],
                'mode':'read_only','hypotheses':[]}

    def weekly_sweep(self, tasks: list[dict], lead_review: dict, ad_report: dict, now: float) -> dict:
        overdue = [t for t in tasks if t.get('status') not in {'done','completed'} and timestamp(t.get('due_at')) is not None and timestamp(t['due_at'])<now]
        priorities = [{'kind':'overdue_task','source':t.get('source'), 'owner':t.get('owner'),'reason':t.get('title')} for t in overdue]
        priorities += [{'kind':'lead_followup','source':r['source'],'reason':r['reason']} for r in lead_review.get('leads',[]) if r['classification']=='Needs follow-up']
        priorities += [{'kind':'campaign_review','reason':flag,'sources':[r['source'] for r in ad_report.get('freshness',[])]} for flag in ad_report.get('flags',[])]
        return {'overdue_tasks':overdue,'priorities':priorities[:3],'missing_sources':ad_report.get('source_failures',[]),'mode':'read_only'}

    @staticmethod
    def pilot_economics(price: float, variable_cost: float, setup_cost: float, monthly_fixed: float,
                        available_hours: float, hours_per_customer: float,
                        manual_minutes: float, review_minutes: float, runs_per_week: int) -> dict:
        values = (price,variable_cost,setup_cost,monthly_fixed,available_hours,hours_per_customer,manual_minutes,review_minutes)
        if any(not math.isfinite(v) or v<0 for v in values) or hours_per_customer<=0 or runs_per_week<0:
            raise ValueError('invalid pilot economics')
        margin = price-variable_cost
        capacity = math.floor(available_hours/hours_per_customer)
        return {'contribution_per_customer':margin,'gross_margin':margin/price if price else None,
                'break_even_customers':math.ceil(monthly_fixed/margin) if margin>0 else None,
                'capacity_customers':capacity,'monthly_profit_at_capacity':capacity*margin-monthly_fixed,
                'setup_payback_months':setup_cost/(capacity*margin-monthly_fixed) if capacity*margin>monthly_fixed else None,
                'hours_saved_weekly':(manual_minutes-review_minutes)*runs_per_week/60,
                'validation_steps':['Interview reachable buyers','Agree on one measurable KPI','Use permissioned data',
                                    'Run a fixed-scope human-reviewed pilot','Validate ten representative cases','Measure paid continuation and review time'],
                'warning':'Input assumptions are hypotheses, not revenue forecasts.'}


    @staticmethod
    def rank_opportunities(cards: list[dict], budget: float, weeks: float,
                           interests: list[str], reachable_buyers: dict[str,int]) -> list[dict]:
        """Evaluate supplied playbook cards; scale labels are not revenue forecasts."""
        if not math.isfinite(budget) or budget<0 or not math.isfinite(weeks) or weeks<=0:
            raise ValueError('valid budget and pilot timeline required')
        ranked = []
        for card in cards:
            required = ('id','title','category','minimum_budget','pilot_weeks','source')
            if any(key not in card for key in required):
                raise ValueError('opportunity card missing provenance or requirements')
            cost,duration = card['minimum_budget'],card['pilot_weeks']
            if not math.isfinite(cost) or cost<0 or not math.isfinite(duration) or duration<=0:
                raise ValueError('invalid opportunity assumptions')
            access = reachable_buyers.get(card['id'],0)
            if type(access) is not int or access<0:
                raise ValueError('reachable buyer counts must be nonnegative integers')
            fit = any(term.lower() in (card['category']+' '+card['title']).lower() for term in interests)
            reasons = []
            if cost>budget:reasons.append('Budget below lean pilot assumption')
            if duration>weeks:reasons.append('Pilot timeline exceeds available time')
            if access<5:reasons.append('Interview access to at least five buyers not established')
            score = 40*min(access/5,1)+20*int(fit)+20*int(cost<=budget)+20*int(duration<=weeks)
            ranked.append({'id':card['id'],'title':card['title'],'source':card['source'],'score':score,
                           'pilot_ready':not reasons,'reasons':reasons,'human_review_required':True})
        return sorted(ranked,key=lambda row:(-row['score'],str(row['id'])))
