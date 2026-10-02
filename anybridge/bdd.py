"""Small runtime Gherkin/BDD layer independent of a particular browser provider."""
from __future__ import annotations
import re
from dataclasses import dataclass,field
from pathlib import Path

@dataclass
class Step:
    keyword:str; text:str; table:list[list[str]]=field(default_factory=list); docstring:str|None=None
@dataclass
class Scenario:
    name:str; steps:list[Step]; tags:list[str]=field(default_factory=list)
@dataclass
class Feature:
    name:str; background:list[Step]; scenarios:list[Scenario]; tags:list[str]=field(default_factory=list)

def parse_feature(source:str)->Feature:
    lines=source.splitlines(); feature=None; background=[]; scenarios=[]; current=None; tags=[]
    pending_tags=[]
    i=0
    while i<len(lines):
        raw=lines[i]; line=raw.strip(); i+=1
        if not line or line.startswith("#"):continue
        if line.startswith("@"): pending_tags += line.split(); continue
        if line.lower().startswith("feature:"):
            feature=line.split(":",1)[1].strip(); continue
        if line.lower()=="background:":
            current=background; continue
        m=re.match(r"(scenario outline|scenario):\s*(.+)",line,re.I)
        if m:
            current=[]; scenarios.append(Scenario(m.group(2).strip(),current,tags+pending_tags)); pending_tags=[]
            continue
        m=re.match(r"(given|when|then|and|but|\*):\s*(.*)",line,re.I)
        if m and current is not None:
            current.append(Step(m.group(1).title(),m.group(2).strip()));continue
        if line.lower()=="examples:" and scenarios:
            # Example tables are retained on the scenario for executor expansion.
            scenarios[-1].steps.append(Step("Examples",""))
            while i<len(lines) and lines[i].strip().startswith("|"):
                cells=[c.strip() for c in lines[i].strip().strip("|").split("|")];scenarios[-1].steps[-1].table.append(cells);i+=1
    if not feature:raise ValueError("Feature file is missing 'Feature:'.")
    return Feature(feature,background,scenarios,pending_tags)

def substitute(text,values):return re.sub(r"<([^>]+)>",lambda m:str(values.get(m.group(1),m.group(0))),text)

class BDDRunner:
    def __init__(self,bridge):
        self.bridge=bridge
        self.steps={}
        self._register_defaults()
    def register(self,pattern,handler):self.steps[re.compile(pattern,re.I)]=handler
    def _register_defaults(self):
        self.register(r"open (?:the )?(?:page|url) (.+)",lambda u:self.bridge.navigate(u))
        self.register(r"navigate to (.+)",lambda u:self.bridge.navigate(u))
        self.register(r"I click (?:on )?(?:the )?(.+)",self._click_text)
        self.register(r"I fill (?:in )?(?:the )?(.+) with (.+)",self._fill_text)
        self.register(r"I should see (.+)",self._assert_text)
        self.register(r"the url should contain (.+)",self._assert_url)
        self.register(r"I wait for (?:the )?text (.+)",lambda t:self.bridge.wait_for(text=t.strip('"')))
    async def _click_text(self,target):
        return await self._find_and_click(target)
    async def _fill_text(self,target,value):
        return await self._find_and_fill(target,value)
    async def _find_and_click(self,target):
        script="return [...document.querySelectorAll('button,a,input,[role=button]')].find(e=>(e.innerText||e.value||e.getAttribute('aria-label')||'').trim().toLowerCase()===arguments[0].toLowerCase());"
        el=await self.bridge._run(self.bridge._driver.execute_script,script,target) if hasattr(self.bridge,"_run") else None
        if el is None:raise AssertionError(f"Element '{target}' was not found.")
        await self.bridge._run(el.click);return await self.bridge.snapshot()
    async def _find_and_fill(self,target,value):
        script="return [...document.querySelectorAll('input,textarea,[contenteditable=true]')].find(e=>(e.name||e.placeholder||e.getAttribute('aria-label')||'').trim().toLowerCase()===arguments[0].toLowerCase());"
        if not hasattr(self.bridge,"_run"):raise RuntimeError("Provider does not expose a native text lookup.")
        el=await self.bridge._run(self.bridge._driver.execute_script,script,target)
        if el is None:raise AssertionError(f"Field '{target}' was not found.")
        await self.bridge._run(el.clear);await self.bridge._run(el.send_keys,value);return await self.bridge.snapshot()
    async def _assert_text(self,text):
        body=await self.bridge.snapshot(interactive_only=False,max_chars=100000)
        assert text.strip('"') in body,f"Expected text not found: {text}"
    async def _assert_url(self,text):
        assert text.strip('"') in self.bridge.current_url,f"Expected URL fragment not found: {text}"
    async def run(self,feature:Feature,variables=None):
        variables=variables or {};results=[]
        for scenario in feature.scenarios:
            example_rows=[{}]
            for st in scenario.steps:
                if st.keyword=="Examples":
                    headers=st.table[0] if st.table else [];example_rows=[dict(zip(headers,row)) for row in st.table[1:]] or [{}]
            for row in example_rows:
                values={**variables,**row};executed=[]
                for st in feature.background+scenario.steps:
                    if st.keyword=="Examples":continue
                    text=substitute(st.text,values)
                    matched=next(((p,h) for p,h in self.steps.items() if p.fullmatch(text)),None)
                    if not matched:raise ValueError(f"Undefined BDD step: {st.keyword} {text}")
                    result=matched[1](*matched[0].match(text).groups())
                    if hasattr(result,"__await__"):await result
                    executed.append(text)
                results.append({"scenario":scenario.name,"steps":executed,"status":"passed"})
        return {"feature":feature.name,"scenarios":results}
