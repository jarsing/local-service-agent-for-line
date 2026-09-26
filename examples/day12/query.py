"""核心測試替身與真實 ADK 分離；雲端必須指定 gemini。"""
class StubQuery:
    mode='STUB_NOT_GEMINI'
    async def ask(self, question, actor, event_id, catalog):
        result=catalog.search({'date':'','area':'花壇','keyword':''})
        return {'mode':self.mode,'result':result,'model_calls':0,'tool_calls':1,
                'events':[{'kind':'STUB_SEARCH','args':{'date':'','area':'花壇','keyword':''}}]}

class QueryFailure(RuntimeError):
    def __init__(self, reason, report):
        super().__init__(reason)
        self.report=report
