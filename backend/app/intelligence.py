"""Deterministic evidence tools, candidate detection and bilingual story frames.

Models select supported stories and presentation frames. Numbers, causal
boundaries and final wording come from these reviewed source-backed frames.
"""
from simulator.clock import event_time, elapsed
from simulator.xg import shot_xg
from .match_store import digest


def build_context(store, time_ms, profile, *, scope=None, since_ms=None):
    # A producer can append several events at the same match timestamp. Freeze
    # the complete context atomically so facts cannot outgrow their snapshot.
    with store.lock:
        return _build_context(store,time_ms,profile,scope=scope,since_ms=since_ms)


def _build_context(store, time_ms, profile, *, scope=None, since_ms=None):
    state=store.snapshot(time_ms)
    rows=store.prefix(time_ms)
    roster={p['player_id']:p for p in store.metadata['players']}
    facts={}
    candidates=[]

    def fact(key,value,unit,team=None,player=None,ids=(),window=None):
        if value is None:return None
        facts[key]={'evidence_id':key,'metric':key,'value':value,'unit':unit,
                    'team_id':team,'player_id':player,'source_event_ids':list(ids),
                    'snapshot_id':state['snapshot_id'],'window':window}
        return key

    goals=[e for e in rows if e['type']=='goal' and e.get('valid_for_statistics') is not False]
    for team in ('home','away'):
        s=state['teams'][team]
        fact(team+'_goals',s['goals'],'goals',team,ids=[e['event_id'] for e in goals if e['team_id']==team])
        fact(team+'_xg',s['xg'],'estimated goals',team,ids=[e['event_id'] for e in rows if e['type']=='shot' and e.get('team_id')==team and e.get('valid_for_statistics') is not False])

    def add(kind,team,event,keys,priority,extra=None):
        keys=[k for k in keys if k and k in facts]
        if not keys:return
        candidates.append({'candidate_id':digest([kind,event.get('event_id'),team,event.get('player_id'),extra]),'kind':kind,
            'team_id':team,'player_id':event.get('player_id'),'event_id':event.get('event_id'),
            'event_time_ms':event_time(store.metadata,event) if event.get('period') else time_ms,
            'claim_ids':keys,'priority':priority,'extra':extra or {}})

    def relevant(e):
        team=profile.team_id or (roster[profile.player_id]['team_id'] if profile.player_id else None)
        actors={e.get(k) for k in ('player_id','player_on_id','player_off_id','victim_id','recipient_id')}
        return (team is None or e.get('team_id')==team) and (not profile.player_id or profile.player_id in actors)

    if scope:
        if scope not in ('full','half','catchup'):raise ValueError('Unknown recap scope')
        start=0 if scope=='full' else elapsed(store.metadata,state['period'],0) if scope=='half' else max(0,time_ms-60000) if since_ms is None else since_ms
        if type(start) not in (int,float) or not 0<=start<=time_ms:raise ValueError('Invalid recap start')
        keys=['home_goals','away_goals']
        for team in ('home','away'):
            window=store.window(start,time_ms,team)
            for metric in ('shots','passes','completed','xg','pressure'):
                key='recap_'+team+'_'+metric
                fact(key,window[metric],'count' if metric!='xg' else 'estimated goals',team,ids=window['event_ids'],window=[start,time_ms])
                if key in facts:keys.append(key)
        moments=[{'type':e['type'],'team_id':e.get('team_id'),'player_id':e.get('player_id'),
                  'event_id':e['event_id'],'time_ms':event_time(store.metadata,e)}
                 for e in rows if start<event_time(store.metadata,e)<=time_ms and e['type'] in ('goal','dismissal','substitution') and e.get('valid_for_statistics') is not False]
        ended={e['period'] for e in rows if e['type']=='period_end'}
        phase='fulltime' if 2 in ended else 'halftime' if 1 in ended and not any(e['period']==2 and e['type'] in ('pass','shot','carry') for e in rows) else 'live'
        add('recap',profile.team_id or 'home',{},keys,100,{'scope':scope,'start_ms':start,'end_ms':time_ms,'phase':phase,'moments':moments[-5:]})
    else:
        for e in reversed(rows):
            age=time_ms-event_time(store.metadata,e)
            if age>120000:break
            if not relevant(e):continue
            kind=e['type'];team=e.get('team_id')
            if team not in ('home','away'):continue
            if e.get('valid_for_statistics') is False and kind!='offside':continue
            if profile.metric_focus=='xg' and kind not in ('shot','goal'):continue
            if profile.metric_focus in ('passing','pressure'):continue
            keys=['home_goals','away_goals'];priority=0
            extra={}
            if kind=='goal':
                priority=100
                if isinstance(e.get('score'),dict) and all(type(e['score'].get(t)) is int for t in ('home','away')):
                    extra['score_keys']={}
                    for t in ('home','away'):
                        key=f"{e['event_id']}_{t}_score"
                        fact(key,e['score'][t],'goals at this goal',t,ids=[e['event_id']])
                        keys.append(key);extra['score_keys'][t]=key
                shot=next((s for s in reversed(rows) if s['event_id']==e.get('shot_event_id') and s['type']=='shot'),None)
                estimate=shot_xg(shot,roster) if shot else None
                if estimate:
                    key='goal_shot_'+shot['event_id']
                    fact(key,estimate['value'],'estimated goals',team,e.get('player_id'),[shot['event_id']])
                    keys.append(key);extra['xg_key']=key
            elif kind=='dismissal':
                priority=95
                extra={'reason':e.get('reason','dismissal')}
            elif kind=='shot':
                estimate=shot_xg(e,roster)
                if not estimate:continue
                key='shot_'+e['event_id']
                fact(key,estimate['value'],'estimated goals',team,e.get('player_id'),[e['event_id']])
                keys.append(key);extra={'outcome':e.get('outcome_reason') or e.get('outcome'),'xg_key':key}
                priority=80 if e.get('set_piece_type')=='penalty' else 65 if estimate['value']>=.12 else 40
            elif kind=='substitution':
                priority=60;extra={'on':e['player_on_id'],'off':e['player_off_id']}
            elif kind=='offside':priority=50
            else:continue
            add(kind,team,e,keys,priority,extra)

        # Compare equal five-minute windows wholly inside the same half.
        if state['period_time_ms']>=600000:
            for team in ('home','away'):
                if profile.team_id and profile.team_id!=team:continue
                if profile.player_id:continue
                current=store.window(time_ms-300000,time_ms,team)
                previous=store.window(time_ms-600000,time_ms-300000,team)
                for metric in ('xg','pressure','completed'):
                    focus={'xg':'xg','pressure':'pressure','completed':'passing'}[metric]
                    if profile.metric_focus not in ('all',focus):continue
                    a,b=current[metric],previous[metric]
                    enough=(a is not None and b is not None and
                            ((metric=='xg' and current['shots']>=2 and a>=b+.15) or
                             (metric=='pressure' and a>=b+3 and a>=4) or
                             (metric=='completed' and current['passes']>=6 and previous['passes']>=6 and a>=b+4)))
                    if not enough:continue
                    keys=[]
                    for prefix,v,window,data in (('current',a,[time_ms-300000,time_ms],current),('previous',b,[time_ms-600000,time_ms-300000],previous)):
                        key=f'{team}_{prefix}_{metric}'
                        keys.append(fact(key,v,'estimated goals' if metric=='xg' else 'count',team,ids=data['event_ids'],window=window))
                    add('trend',team,{},keys,70,{'metric':metric})

        if profile.player_id:
            p=state['players'][profile.player_id]
            if p['minutes_played_ms']>0:
                keys=[]
                for metric in ('goals','xg','assists'):
                    keys.append(fact('player_'+metric,p[metric],'estimated goals' if metric=='xg' else 'count',p['team_id'],profile.player_id,
                                     [e['event_id'] for e in rows if e.get('player_id')==profile.player_id]))
                add('player',p['team_id'],{'player_id':profile.player_id},keys,55)
        # Match-local milestones need no external career/season history.
        if not profile.player_id and profile.metric_focus in ('all','passing'):
            for team in ('home','away'):
                if profile.team_id and profile.team_id!=team:continue
                complete=[e for e in rows if e['type']=='pass' and e.get('team_id')==team and e.get('outcome')=='complete' and e.get('valid_for_statistics') is not False]
                threshold=len(complete)//50*50
                if threshold:
                    event=complete[threshold-1]
                    if time_ms-event_time(store.metadata,event)<=120000:
                        key=f'{team}_passing_milestone_{threshold}'
                        fact(key,threshold,'completed passes',team,ids=[e['event_id'] for e in complete[:threshold]])
                        add('milestone',team,event,[key],52,{'threshold':threshold})
    candidates.sort(key=lambda c:(c['priority'],c['event_time_ms']),reverse=True)
    critical=[c for c in candidates if c['priority']>=95]
    if critical:candidates=critical
    return {'state':state,'facts':facts,'candidates':candidates[:4],
            'names':{p:r['name'] for p,r in roster.items()},
            'teams':{t['team_id']:t['name'] for t in store.metadata['teams']}}


def tool_context(context,candidate_id):
    candidate=next((c for c in context['candidates'] if c['candidate_id']==candidate_id),None)
    if not candidate:raise ValueError('Unknown candidate; tool is confined to this snapshot')
    return {'candidate':candidate,'snapshot_id':context['state']['snapshot_id'],
            'as_of_match_time_ms':context['state']['as_of_match_time_ms'],
            'facts':[context['facts'][k] for k in candidate['claim_ids']],
            'limitations':['Synthetic events; xG is an uncalibrated estimate; no causal or historical claims.']}


def render_story(context,candidate,profile,frame,style):
    """The model selects a frame; values and bilingual wording remain verifiable."""
    f=context['facts'];team=context['teams'][candidate['team_id']]
    player=context['names'].get(candidate.get('player_id'),team)
    v=lambda key:f[key]['value']
    number=lambda key: '—' if key not in f else str(v(key)) if type(v(key)) is int else f'{v(key):.2f}'
    hi=profile.locale=='hi';kind=candidate['kind'];x=candidate['extra']
    score=f"{number('home_goals')}–{number('away_goals')}"
    if kind=='goal':
        headline=f'{player} ने गोल किया' if hi else f'{player} changes the scoreline'
        score_keys=x.get('score_keys',{'home':'home_goals','away':'away_goals'})
        score=f"{number(score_keys['home'])}–{number(score_keys['away'])}"
        own=v(score_keys[candidate['team_id']]);other=v(score_keys['away' if candidate['team_id']=='home' else 'home'])
        en,translation=('draw level','बराबरी पर आ गई') if own==other else ('take the lead','बढ़त में आ गई') if own==other+1 else ('extend their lead','अपनी बढ़त बढ़ाती है') if own>other else ('reduce the deficit','अंतर कम करती है')
        why=f'इस गोल से स्कोर {score} हुआ; {team} {translation}।' if hi else f'This goal made it {score}; {team} {en}.'
        if x.get('xg_key'):
            quality=number(x['xg_key'])
            why+=f' गोल वाले शॉट का अनुमानित xG {quality} था। यह मौके की गुणवत्ता है, नतीजे का पूर्वानुमान नहीं।' if hi else f' The scoring shot had {quality} estimated xG, describing the chance quality before its outcome.'
    elif kind=='shot':
        quality=number(x['xg_key'])
        headline=f'{player} का मौका' if hi else f'A chance for {player}'
        why=f'इस शॉट का अनुमानित xG {quality} है। यह मौके की गुणवत्ता का संकेत है, गोल होने की गारंटी नहीं।' if hi else f'This attempt carries {quality} estimated xG: context for the quality of the chance, rather than a guarantee of a goal.'
        why+=f' स्कोर {score} है।' if hi else f' The score is {score}.'
    elif kind=='dismissal':
        headline=f'{team} के खिलाड़ी को बाहर भेजा गया' if hi else f'{team} lose a player to dismissal'
        why='इस खिलाड़ी के अगले योगदान बंद हो गए हैं; आगे की घटनाओं को बदली हुई खिलाड़ी संख्या के साथ देखें।' if hi else 'The dismissed player can no longer contribute. Subsequent phases now have a changed on-pitch player count.'
    elif kind=='substitution':
        on=context['names'][x['on']];off=context['names'][x['off']]
        headline=f'{team} का बदलाव' if hi else f'A fresh face for {team}'
        why=f'{on} ने {off} की जगह ली। नए खिलाड़ी की रेटिंग और आँकड़े उनके मैदान में आने से जुड़ते हैं।' if hi else f'{on} comes on for {off}. From here, we’ll follow their minutes, contributions and match rating as the game unfolds.'
    elif kind=='offside':
        headline='ऑफसाइड ने हमले को रोका' if hi else 'Offside interrupts the attack'
        why='अमान्य हमले के शॉट या गोल आँकड़ों में नहीं जुड़ते। इसे एक वैध मौके की तरह न पढ़ें।' if hi else 'The invalid attack does not earn shot or goal credit. Treat the interruption separately from a valid scoring chance.'
    elif kind=='trend':
        a,b=[number(key) for key in candidate['claim_ids']]
        labels={'xg':('estimated xG','अनुमानित xG'),'pressure':('pressure observations','दबाव की दर्ज घटनाएँ'),'completed':('completed passes','सफल पास')}
        en,hindi=labels[x['metric']]
        headline=f'{team}: हाल के खेल में बदलाव' if hi else f'{team}: a shift in the recent pattern'
        why=f'पिछले पाँच मिनट में {hindi} {a} हैं; उससे पहले के पाँच मिनट में {b} थे। यह दर्ज घटनाओं की तुलना है, रणनीति का प्रमाण नहीं।' if hi else f'The latest five minutes contain {a} {en}, versus {b} in the preceding five. This is an observed change, not proof of a tactical cause.'
    elif kind=='player':
        headline=f'{player}: खिलाड़ी पर नज़र' if hi else f'{player}: the contribution so far'
        why=f"गोल {number('player_goals')}, असिस्ट {number('player_assists')}, अनुमानित xG {number('player_xg')}। आँकड़े केवल अब तक की घटनाओं से हैं।" if hi else f"{number('player_goals')} goals, {number('player_assists')} assists and {number('player_xg')} estimated xG, from completed events at this replay position."
    elif kind=='recap':
        headline={'full':('Match recap so far','अब तक के मैच का सार'),'half':('This half so far','इस हाफ का सार'),'catchup':('Your catch-up','आपके लिए सार')}[x['scope']][1 if hi else 0]
        chunks=[]
        for t in ('home','away'):
            name=context['teams'][t];shots=number('recap_'+t+'_shots');passes=number('recap_'+t+'_passes');completed=number('recap_'+t+'_completed')
            shot_word='shot' if shots=='1' else 'shots'
            pass_word='pass' if passes=='1' else 'passes'
            chunks.append(f'{name}: {shots} शॉट; {passes} में से {completed} पास सफल।' if hi else f'{name}: {shots} {shot_word}, with {completed} of {passes} {pass_word} completed in this spell.')
        why=(f'वर्तमान स्कोर {score}। ' if hi else f'Current score: {score}. ')+' '.join(chunks)
        if x['phase'] in ('halftime','fulltime'):
            headline={'halftime':('Halftime recap','मध्यांतर का सार'),'fulltime':('Full-time recap','मैच का अंतिम सार')}[x['phase']][1 if hi else 0]
        highlights=[]
        for event in x['moments']:
            name=context['names'].get(event['player_id'],context['teams'].get(event['team_id'],''))
            action={'goal':('scored','ने गोल किया'),'dismissal':('was dismissed','को बाहर भेजा गया'),'substitution':('was involved in a substitution','बदलाव में शामिल थे')}[event['type']][1 if hi else 0]
            highlights.append(f'{name} {action}')
        if highlights:why+=(' मुख्य घटनाएँ: ' if hi else ' Key moments: ')+'; '.join(highlights)+'.'
    elif kind=='milestone':
        n=x['threshold']
        headline=f'{team}: सफल पास की उपलब्धि' if hi else f'{team} reach a passing milestone'
        why=f'इस मैच में {n} सफल पास पूरे हुए। यह इसी मैच की उपलब्धि है, करियर या सीज़न का रिकॉर्ड नहीं।' if hi else f'The team reached {n} completed passes in this match. This marks accumulated ball circulation, not a career or season record.'
    else:raise ValueError('Unsupported story kind')
    if style in ('technical','comparison'):
        details='; '.join(f"{key}={number(key)} {f[key]['unit']}" for key in candidate['claim_ids'])
        why+=(' तथ्य: ' if hi else ' Evidence: ')+details+'.'
    elif style=='supporter':
        why+=(' पसंदीदा टीम का संदर्भ; तथ्य दोनों दर्शकों के लिए समान हैं।' if hi else 'Your team focus changes relevance, while the underlying facts stay the same.')
    if frame=='numbers' and style not in ('technical','comparison'):
        why+=(' पूरा विवरण साक्ष्य में है।' if hi else ' Open the evidence for the exact values and source events.')
    return headline,why
