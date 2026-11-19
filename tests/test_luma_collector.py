from opportunity_engine.collectors.luma import Luma
class Resp:
 def raise_for_status(self):pass
 def json(self):return {'entries':[{'api_id':'evt-1','event':{'api_id':'evt-1','name':'AI Night','url':'ai-night','geo_address_info':{'city':'Toronto'}}}]}
class Client:
 def get(self,*a,**k):return Resp()
def test_luma_fixture_parser():
 items=Luma(queries=['Toronto'],client=Client(),sleep=lambda _:None).fetch()
 assert items[0].source_id=='evt-1' and items[0].url.endswith('/ai-night')
