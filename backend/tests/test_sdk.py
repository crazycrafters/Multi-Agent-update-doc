import json
import httpx
from openai import AsyncOpenAI
from app.agents import OpenAIProvider
from app.config import Settings
from app.schemas import Question

async def test_real_sdk_structured_output_and_web_search_transport():
    requests=[]
    async def handler(request):
        body=json.loads(request.content);requests.append(body)
        text=json.dumps({'text':'Explain your actual contribution','claim_ids':[],'difficulty':'target-role'}) if 'tools' not in body else 'Public guidance'
        output=[{'id':'msg_test','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':text,'annotations':[] if 'tools' not in body else [{'type':'url_citation','url':'https://docs.python.org/3/','title':'Python docs','start_index':0,'end_index':10}]}]}]
        if 'tools' in body:output.insert(0,{'id':'ws_test','type':'web_search_call','status':'completed','action':{'type':'search','query':'validation','sources':[{'type':'url','url':'https://docs.python.org/3/'}]}})
        return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':1,'model':'gpt-4.1-mini','status':'completed','output':output,'usage':{'input_tokens':10,'output_tokens':20,'total_tokens':30}})
    provider=OpenAIProvider(Settings(openai_api_key='test-not-a-real-key'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider.client=AsyncOpenAI(api_key='test-not-a-real-key',http_client=client)
        result=await provider.generate('interviewer','Ask one question',{'target_role':'Nurse'},Question)
        assert result.data['text']=='Explain your actual contribution' and result.input_tokens==10
        result=await provider.research(['validation'])
        assert result.search_calls==1 and result.data['sources'][0]['url']=='https://docs.python.org/3/'
        assert requests[0]['store'] is False and requests[0]['text']['format']['strict']
        assert requests[1]['tools']==[{'type':'web_search'}]
        assert 'Nurse' not in requests[1]['input']
