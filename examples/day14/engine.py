"""單回合工具邊界：模型可查資料與提議記憶，不能保存同意或改寫帳號。"""
from __future__ import annotations
from .places import PlacesCatalog, diet, bounded

TOOL_FIELDS={
    'search_local_places':('area','dietary_type','keyword'),
    'search_local_events':('date','area','keyword'),
    'propose_dietary_memory':('dietary_type','area','keyword'),
    'show_local_help':('reason',),
    'request_memory_management':('action','dietary_type'),
}

class TurnTools:
    def __init__(self,memory,actor,*,places=None,events=None,clock=None):
        self.memory,self.actor=memory,actor
        self.snapshot=memory.inspect(actor)
        self.places=places or PlacesCatalog();self.events=events
        self.clock=clock or memory.clock;self.calls=[];self.last=None

    def execute(self,name,args):
        if name not in TOOL_FIELDS or not isinstance(args,dict) or set(args)-set(TOOL_FIELDS[name]):
            raise ValueError('UNSUPPORTED_TOOL_ARGUMENTS')
        if self.calls: raise ValueError('ONE_BUSINESS_TOOL_PER_TURN')
        normalized={k:args.get(k,'') for k in TOOL_FIELDS[name]}
        for k,v in normalized.items(): bounded(v,k,100)
        # Same account/permission and latest generation both before and after the read.
        self.memory.assert_revision(self.actor,self.snapshot['revision'])
        record={'tool':name,'proposed_arguments':dict(normalized),'memory_revision':self.snapshot['revision']}
        if name=='search_local_places':
            requested=diet(normalized['dietary_type'])
            effective=(self.snapshot['dietary_type'] or 'any') if normalized['dietary_type']=='' else requested
            origin='consented_memory' if normalized['dietary_type']=='' and self.snapshot['dietary_type'] else 'this_turn' if normalized['dietary_type'] else 'none'
            params={**normalized,'dietary_type':effective}
            result=self.places.search(**params,now=self.clock())
            result.update(preference_origin=origin,memory_revision=self.snapshot['revision'])
            record.update(effective_arguments=result['query'],preference_origin=origin,place_ids=[p['place_id'] for p in result['places']])
        elif name=='search_local_events':
            if self.events is None: raise ValueError('EVENT_CATALOG_REQUIRED')
            result={'status':'events_result','catalog_result':self.events.search(normalized),'memory_revision':self.snapshot['revision']}
            record['effective_arguments']=normalized
        elif name=='propose_dietary_memory':
            value=diet(normalized['dietary_type'],allow_any=False)
            result={'status':'memory_proposal_requested','dietary_type':value,'area':normalized['area'],
                    'keyword':normalized['keyword'],'memory_revision':self.snapshot['revision'],
                    'stored':False,'requires_user_confirmation':True}
        elif name=='request_memory_management':
            if normalized['action'] not in ('inspect','update','forget'): raise ValueError('MEMORY_ACTION')
            value=diet(normalized['dietary_type'],allow_any=False) if normalized['dietary_type'] else ''
            result={'status':'memory_management_requested','action':normalized['action'],'dietary_type':value,
                    'memory_revision':self.snapshot['revision'],'requires_user_confirmation':normalized['action']!='inspect'}
        else:
            result={'status':'help','reason':bounded(normalized['reason'],'reason'),
                    'memory_revision':self.snapshot['revision']}
        self.memory.assert_revision(self.actor,self.snapshot['revision'])
        self.calls.append(record);self.last=result
        return result

class ScriptedInterpreter:
    """TEST ONLY: explicit model-call replacement, never a measured Gemini success."""
    mode='SCRIPTED_INTENT_NOT_GEMINI'
    def __init__(self,mapping=None): self.mapping=mapping or {}
    async def ask(self,text,actor,event_id,tools):
        name,args=self.mapping.get(text,('show_local_help',{'reason':'unsupported'}))
        result=tools.execute(name,args)
        return {'mode':self.mode,'result':result,'tool_events':tools.calls,'model_calls':0,'tool_calls':1}
