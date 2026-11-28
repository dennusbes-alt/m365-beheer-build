import { useEffect, useState } from 'react';
import { startTab } from '../store.jsx';
import { CheckCircle2, Fish, KeyRound, Pencil, Plus, RefreshCw, RotateCw, ShieldAlert, Trash2, XCircle } from 'lucide-react';
import { act } from '../api.js';
import { Msg, ask, openModal } from '../overlays.jsx';
import { useApp } from '../store.jsx';
import { Btn, Card, Check, Chip, Field, Loading, Tabs, dt } from '../ui.jsx';

export default function Bedreiging() {
  const { info } = useApp();
  const [tab, setTab] = useState(() => startTab('bedreiging', 'spam'));
  if (info.exo === false) return <><h2>Bedreigingsbeheer</h2><Msg kind="err">Exchange Online is niet verbonden bij deze klant.</Msg></>;
  return (
    <>
      <h2>Bedreigingsbeheer</h2>
      <p className="sub">Anti-spam- en anti-phishingbeleid en DKIM-ondertekening per domein.</p>
      <Tabs value={tab} onChange={setTab} tabs={[['spam', 'Anti-spam', ShieldAlert], ['phish', 'Anti-phishing', Fish], ['dkim', 'DKIM', KeyRound]]} />
      {tab === 'dkim' ? <Dkim /> : <Beleid key={tab} kind={tab} />}
    </>
  );
}

// ---------------- Velddefinities ----------------
const ACTIE_SPAM = [['MoveToJmf', 'Naar map Ongewenste e-mail'], ['Quarantine', 'Quarantaine'], ['AddXHeader', 'X-header toevoegen'],
  ['ModifySubject', 'Onderwerp aanpassen'], ['Redirect', 'Omleiden'], ['Delete', 'Verwijderen']];
const AAN_UIT_TEST = [['Off', 'Uit'], ['On', 'Aan'], ['Test', 'Test']];
const SPAM_GROEPEN = [
  ['Drempelwaarden', [
    ['BulkThreshold', 'Bulkmail-drempel (1 = streng, 9 = soepel)', 'num'],
    ['MarkAsSpamBulkMail', 'Bulkmail als spam markeren', ['On', 'Off']],
    ['QuarantineRetentionPeriod', 'Dagen in quarantaine bewaren (1-30)', 'num'],
  ]],
  ['Spameigenschappen: score verhogen', [
    ['IncreaseScoreWithImageLinks', 'Afbeeldingslinks naar externe sites', AAN_UIT_TEST], ['IncreaseScoreWithNumericIps', 'Numerieke IP-adressen in URL', AAN_UIT_TEST],
    ['IncreaseScoreWithRedirectToOtherPort', 'URL omleiden naar andere poort', AAN_UIT_TEST], ['IncreaseScoreWithBizOrInfoUrls', 'Links naar .biz- of .info-sites', AAN_UIT_TEST],
  ]],
  ['Spameigenschappen: als spam markeren', [
    ['MarkAsSpamEmptyMessages', 'Lege berichten', AAN_UIT_TEST], ['MarkAsSpamJavaScriptInHtml', 'JavaScript of VBScript in HTML', AAN_UIT_TEST],
    ['MarkAsSpamFramesInHtml', 'Frames in HTML', AAN_UIT_TEST], ['MarkAsSpamObjectTagsInHtml', 'Object-tags in HTML', AAN_UIT_TEST],
    ['MarkAsSpamEmbedTagsInHtml', 'Embed-tags in HTML', AAN_UIT_TEST], ['MarkAsSpamFormTagsInHtml', 'Formulieren in HTML', AAN_UIT_TEST],
    ['MarkAsSpamWebBugsInHtml', 'Webbugs (trackingpixels)', AAN_UIT_TEST], ['MarkAsSpamSensitiveWordList', 'Gevoelige woorden', AAN_UIT_TEST],
    ['MarkAsSpamSpfRecordHardFail', 'SPF hard fail', AAN_UIT_TEST], ['MarkAsSpamFromAddressAuthFail', 'Afzender-ID mislukt', AAN_UIT_TEST],
    ['MarkAsSpamNdrBackscatter', 'Backscatter (onterechte NDR\'s)', AAN_UIT_TEST],
  ]],
  ['Acties', [
    ['SpamAction', 'Spam', ACTIE_SPAM], ['HighConfidenceSpamAction', 'Spam met hoge zekerheid', ACTIE_SPAM],
    ['PhishSpamAction', 'Phishing', ACTIE_SPAM], ['HighConfidencePhishAction', 'Phishing met hoge zekerheid', [['Quarantine', 'Quarantaine'], ['Redirect', 'Omleiden'], ['Delete', 'Verwijderen']]],
    ['BulkSpamAction', 'Bulkmail', ACTIE_SPAM], ['ModifySubjectValue', 'Tekst voor onderwerp (bij "Onderwerp aanpassen")', 'text'],
    ['AddXHeaderValue', 'X-header (bij "X-header toevoegen")', 'text'], ['InlineSafetyTipsEnabled', 'Veiligheidstips tonen', 'bool'],
    ['SpamZapEnabled', 'Achteraf opschonen spam (ZAP)', 'bool'], ['PhishZapEnabled', 'Achteraf opschonen phishing (ZAP)', 'bool'],
  ]],
  ['Toegestaan en geblokkeerd', [
    ['AllowedSenders', 'Toegestane afzenders', 'list'], ['AllowedSenderDomains', 'Toegestane domeinen', 'list'],
    ['BlockedSenders', 'Geblokkeerde afzenders', 'list'], ['BlockedSenderDomains', 'Geblokkeerde domeinen', 'list'],
  ]],
];
const ACTIE_PHISH = [['MoveToJmf', 'Naar map Ongewenste e-mail'], ['Quarantine', 'Quarantaine'], ['Redirect', 'Omleiden'], ['Delete', 'Verwijderen'], ['NoAction', 'Geen actie']];
const PHISH_GROEPEN = [
  ['Beveiligingsinstellingen', [
    ['Enabled', 'Beleid actief', 'bool'],
    ['PhishThresholdLevel', 'Phishingdrempel', [['1', '1 - Standaard'], ['2', '2 - Agressief'], ['3', '3 - Agressiever'], ['4', '4 - Meest agressief']]],
    ['EnableSpoofIntelligence', 'Spoofing-intelligentie', 'bool'], ['HonorDmarcPolicy', 'DMARC-beleid van afzender volgen', 'bool'],
    ['EnableUnauthenticatedSender', 'Vraagteken bij niet-geverifieerde afzender', 'bool'], ['EnableViaTag', '"via"-label tonen', 'bool'],
    ['EnableFirstContactSafetyTips', 'Tip bij eerste contact', 'bool'],
  ]],
  ['Imitatiebeveiliging (Defender for Office 365)', [
    ['EnableMailboxIntelligence', 'Postvakintelligentie', 'bool'], ['EnableMailboxIntelligenceProtection', 'Beveiliging op basis van postvakintelligentie', 'bool'],
    ['EnableTargetedUserProtection', 'Gebruikers beschermen tegen imitatie', 'bool'], ['TargetedUsersToProtect', 'Te beschermen gebruikers (Naam;adres)', 'list'],
    ['EnableOrganizationDomainsProtection', 'Eigen domeinen beschermen', 'bool'], ['EnableTargetedDomainsProtection', 'Extra domeinen beschermen', 'bool'],
    ['TargetedDomainsToProtect', 'Extra te beschermen domeinen', 'list'], ['ExcludedSenders', 'Vertrouwde afzenders', 'list'], ['ExcludedDomains', 'Vertrouwde domeinen', 'list'],
    ['EnableSimilarUsersSafetyTips', 'Tip bij vergelijkbare gebruikersnaam', 'bool'], ['EnableSimilarDomainsSafetyTips', 'Tip bij vergelijkbaar domein', 'bool'],
    ['EnableUnusualCharactersSafetyTips', 'Tip bij ongebruikelijke tekens', 'bool'],
  ]],
  ['Acties', [
    ['AuthenticationFailAction', 'Bij spoofing', [['MoveToJmf', 'Naar map Ongewenste e-mail'], ['Quarantine', 'Quarantaine']]],
    ['DmarcQuarantineAction', 'DMARC p=quarantine', [['Quarantine', 'Quarantaine'], ['MoveToJmf', 'Naar map Ongewenste e-mail']]],
    ['DmarcRejectAction', 'DMARC p=reject', [['Reject', 'Weigeren'], ['Quarantine', 'Quarantaine']]],
    ['TargetedUserProtectionAction', 'Bij imitatie van gebruiker', ACTIE_PHISH], ['TargetedDomainProtectionAction', 'Bij imitatie van domein', ACTIE_PHISH],
    ['MailboxIntelligenceProtectionAction', 'Bij imitatie (postvakintelligentie)', ACTIE_PHISH],
  ]],
];

function Veld({ def, waarde, zet }) {
  const [k, label, soort] = def;
  if (soort === 'bool') return <Check checked={waarde === true || waarde === 'True'} onChange={(v) => zet(k, v)}>{label}</Check>;
  if (soort === 'list') return <div><label className="f">{label}</label><textarea rows={3} value={Array.isArray(waarde) ? waarde.join('\n') : (waarde || '')} onChange={(e) => zet(k, e.target.value.split(/\n/))} placeholder="Eén per regel" /></div>;
  if (soort === 'num') return <Field label={label} type="number" value={waarde ?? ''} onChange={(v) => zet(k, v === '' ? null : Number(v))} />;
  if (soort === 'text') return <Field label={label} value={waarde ?? ''} onChange={(v) => zet(k, v)} />;
  return (
    <div><label className="f">{label}</label>
      <select value={waarde == null ? '' : String(waarde)} onChange={(e) => zet(k, e.target.value)}>
        {waarde != null && !soort.some(([v]) => v === String(waarde)) && <option value={String(waarde)}>{String(waarde)}</option>}
        {soort.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select></div>
  );
}

function BeleidBewerken({ kind, naam, close }) {
  const [d, setD] = useState(null);
  const [wijz, setWijz] = useState({});
  useEffect(() => { act('threat.get', { kind, name: naam }).then((x) => setD(x || { props: {} })); }, [kind, naam]);
  if (!d) return <Loading />;
  const groepen = kind === 'spam' ? SPAM_GROEPEN : PHISH_GROEPEN;
  const waarde = (k) => (k in wijz ? wijz[k] : d.props[k]);
  const zet = (k, v) => setWijz({ ...wijz, [k]: v });
  return (
    <>
      <h3>{naam}</h3>
      {groepen.map(([titel, velden]) => {
        const zichtbaar = velden.filter((v) => v[0] in d.props);
        if (!zichtbaar.length) return null;
        return (
          <div key={titel} style={{ marginBottom: 10 }}>
            <h4 style={{ margin: '12px 0 2px', color: 'var(--navy)' }}>{titel}</h4>
            <div className="cols2" style={{ gap: '0 18px' }}>{zichtbaar.map((v) => <Veld key={v[0]} def={v} waarde={waarde(v[0])} zet={zet} />)}</div>
          </div>
        );
      })}
      {kind === 'phish' && !('EnableMailboxIntelligence' in d.props) && <Msg kind="info">Imitatiebeveiliging is niet beschikbaar: deze klant heeft geen Defender for Office 365.</Msg>}
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" disabled={!Object.keys(wijz).length} onClick={() => close(wijz)}>Opslaan</Btn></div>
    </>
  );
}

function NieuwBeleid({ kind, close }) {
  const [f, setF] = useState({ name: '', domains: '', users: '', groups: '', priority: '' });
  const z = (k) => (v) => setF({ ...f, [k]: v });
  return (
    <>
      <h3>Nieuw {kind === 'spam' ? 'anti-spambeleid' : 'anti-phishingbeleid'}</h3>
      <Field label="Naam *" value={f.name} onChange={z('name')} autoFocus />
      <p className="hint">Voor wie geldt het? Vul minimaal één van de drie in (komma-gescheiden). Daarna kun je de instellingen bewerken.</p>
      <Field label="Ontvangerdomeinen" value={f.domains} onChange={z('domains')} placeholder="domein.nl" />
      <Field label="Gebruikers" value={f.users} onChange={z('users')} placeholder="naam@domein.nl" />
      <Field label="Groepen (e-mailadres)" value={f.groups} onChange={z('groups')} />
      <Field label="Prioriteit (0 = hoogst, leeg = laatst)" value={f.priority} onChange={z('priority')} type="number" />
      <div className="foot"><Btn onClick={() => close(null)}>Annuleren</Btn><Btn v="p" disabled={!f.name.trim() || !(f.domains || f.users || f.groups)} onClick={() => close(f)}>Aanmaken</Btn></div>
    </>
  );
}

function Beleid({ kind }) {
  const [d, setD] = useState(null);
  const laad = async () => { setD(null); const x = await act('threat.list', { kind }); setD(x ? x.policies : []); };
  useEffect(() => { laad(); }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <Loading text="Beleid ophalen..." />;
  const bewerk = async (p) => {
    const w = await openModal((close) => <BeleidBewerken kind={kind} naam={p.name} close={close} />, { wide: true });
    if (w && await act('threat.set', { kind, name: p.name, props: w }, { msg: 'Opslaan...' })) laad();
  };
  const nieuw = async () => {
    const f = await openModal((close) => <NieuwBeleid kind={kind} close={close} />, { wide: true });
    if (f && await act('threat.create', { kind, ...f }, { msg: 'Aanmaken...' })) { await laad(); bewerk({ name: f.name.trim() }); }
  };
  return (
    <Card title={kind === 'spam' ? 'Anti-spambeleid' : 'Anti-phishingbeleid'} icon={kind === 'spam' ? ShieldAlert : Fish}
      right={<div className="btns"><Btn s v="p" icon={Plus} onClick={nieuw}>Nieuw beleid</Btn><Btn s icon={RefreshCw} onClick={laad} /></div>}>
      <table>
        <thead><tr><th>Prio</th><th>Naam</th><th>Geldt voor</th><th>Status</th><th /></tr></thead>
        <tbody>{d.map((p) => (
          <tr key={p.name} className={p.preset ? '' : 'click'} onClick={() => !p.preset && bewerk(p)}>
            <td style={{ width: 80 }} onClick={(e) => e.stopPropagation()}>
              {p.default ? <span className="hint">Laagst</span> : <input type="number" min={0} defaultValue={p.priority} style={{ width: 60 }}
                onBlur={(e) => { if (String(e.target.value) !== String(p.priority)) act('threat.rule', { kind, rule: p.rule, priority: e.target.value }).then(laad); }} />}
            </td>
            <td><b>{p.preset ? (p.name.startsWith('Strict') ? 'Strenge voorinstelling' : 'Standaardvoorinstelling') : p.name}</b>{p.default && <> <Chip k="mu">standaard</Chip></>}{p.preset && <> <Chip k="mu">Microsoft-voorinstelling</Chip></>}</td>
            <td style={{ fontSize: 12.5 }}>{p.default ? 'Iedereen (als geen ander beleid geldt)' : [...p.domains, ...p.users, ...p.groups].join(', ') || '-'}</td>
            <td>{p.state === 'Enabled' || p.default ? <Chip k="g">{p.default ? 'Altijd aan' : 'Aan'}</Chip> : <Chip k="mu">{p.state === 'Disabled' ? 'Uit' : p.state}</Chip>}</td>
            <td className="r" onClick={(e) => e.stopPropagation()}><div className="btns" style={{ justifyContent: 'flex-end' }}>
              {!p.preset && <Btn s icon={Pencil} onClick={() => bewerk(p)}>Bewerken</Btn>}
              {!p.default && !p.preset && p.rule && <Btn s onClick={async () => { if (await act('threat.rule', { kind, rule: p.rule, enabled: p.state !== 'Enabled' })) laad(); }}>{p.state === 'Enabled' ? 'Uitzetten' : 'Aanzetten'}</Btn>}
              {!p.default && !p.preset && <Btn s v="dl" icon={Trash2} onClick={async () => { if (await ask(`Beleid '${p.name}' en de bijbehorende regel verwijderen?`, 'Verwijderen', true) && await act('threat.delete', { kind, name: p.name })) laad(); }} />}
            </div></td>
          </tr>))}</tbody>
      </table>
      <div className="hint">Klik op een beleid om drempelwaarden, acties en (bij anti-spam) toegestane en geblokkeerde afzenders te bewerken. Een lager prioriteitsnummer gaat voor.</div>
    </Card>
  );
}

// ---------------- DKIM ----------------
function Dkim() {
  const [d, setD] = useState(null);
  const laad = async () => { const x = await act('dkim.list', {}); setD(x ? x.domains : []); };
  useEffect(() => { laad(); }, []);
  if (!d) return <Loading text="Domeinen ophalen..." />;
  const open = async (dom) => { await openModal((close) => <DkimDomein domein={dom} close={close} />, { wide: true }); laad(); };
  return (
    <Card title="DKIM per domein" icon={KeyRound} right={<Btn s icon={RefreshCw} onClick={laad} />}>
      <table>
        <thead><tr><th>Domein</th><th>DKIM</th><th>Status</th><th /></tr></thead>
        <tbody>{d.map((x) => (
          <tr key={x.domain} className="click" onClick={() => open(x.domain)}>
            <td><b>{x.domain}</b>{x.default && <> <Chip k="mu">standaard</Chip></>}{x.onmicrosoft && <> <Chip k="mu">Microsoft-domein</Chip></>}</td>
            <td>{x.enabled ? <Chip k="g">Aan</Chip> : x.configured ? <Chip k="o">Uit</Chip> : <Chip k="r">Niet ingesteld</Chip>}</td>
            <td className="hint">{x.status}</td>
            <td className="r"><Btn s>Openen</Btn></td>
          </tr>))}</tbody>
      </table>
    </Card>
  );
}

function DkimDomein({ domein, close }) {
  const [d, setD] = useState(null);
  const laad = async () => { const x = await act('dkim.get', { domain: domein }); setD(x || { configured: false }); };
  useEffect(() => { laad(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const doe = async (naam, body, msg) => { const x = await act(naam, { domain: domein, ...body }, { msg }); if (x) setD(x); };
  return (
    <>
      <h3>DKIM voor {domein}</h3>
      {!d ? <Loading /> : !d.configured ? (
        <>
          <p>DKIM is voor dit domein nog niet ingesteld. Instellen maakt de sleutels aan; daarna zet je twee CNAME-records in de DNS en schakel je DKIM in.</p>
          <Btn v="p" icon={KeyRound} onClick={() => doe('dkim.create', {}, 'DKIM instellen...')}>DKIM instellen</Btn>
        </>
      ) : (
        <>
          <div className="kv" style={{ marginBottom: 12 }}>
            <div><label>Status</label><div>{d.enabled ? <Chip k="g">Ingeschakeld</Chip> : <Chip k="o">Uitgeschakeld</Chip>} <span className="hint">{d.status}</span></div></div>
            <div><label>Sleutelgrootte</label><div>{d.keySize || '-'} bits</div></div>
            <div><label>Sleutel aangemaakt</label><div>{dt(d.created)}</div></div>
            <div><label>Rotatie gepland</label><div>{dt(d.rotateOn)}</div></div>
          </div>
          {!d.onmicrosoft && (
            <>
              <h4 style={{ margin: '8px 0 4px', color: 'var(--navy)' }}>DNS-records (CNAME)</h4>
              <table>
                <thead><tr><th /><th>Naam</th><th>Moet verwijzen naar</th><th>Nu in DNS</th></tr></thead>
                <tbody>{d.records.map((r) => (
                  <tr key={r.name}>
                    <td>{r.ok ? <CheckCircle2 size={17} color="var(--gr)" /> : <XCircle size={17} color="var(--rd)" />}</td>
                    <td style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace', fontSize: 12.5 }}>{r.name}</td>
                    <td style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace', fontSize: 12.5, wordBreak: 'break-all' }}>{r.value}</td>
                    <td style={{ fontSize: 12.5, wordBreak: 'break-all' }}>{r.current || <span style={{ color: 'var(--rd)' }}>ontbreekt</span>}</td>
                  </tr>))}</tbody>
              </table>
              {d.records.some((r) => !r.ok) && <Msg kind="warn">Niet alle records staan goed. Zet ze bij de DNS-provider van het domein; daarna kan DKIM aan. DNS-wijzigingen kunnen even duren.</Msg>}
            </>
          )}
          <div className="btns" style={{ marginTop: 12 }}>
            {d.enabled
              ? <Btn v="dl" onClick={async () => { if (await ask(`DKIM uitschakelen voor ${domein}?`, 'Uitschakelen', true)) doe('dkim.set', { enabled: false }, 'Uitschakelen...'); }}>DKIM uitschakelen</Btn>
              : <Btn v="p" onClick={() => doe('dkim.set', { enabled: true }, 'Inschakelen...')}>DKIM inschakelen</Btn>}
            {d.enabled && <Btn icon={RotateCw} onClick={async () => { if (await ask(`De DKIM-sleutels van ${domein} roteren? De nieuwe sleutel wordt binnen enkele dagen actief.`, 'Roteren')) doe('dkim.rotate', {}, 'Roteren...'); }}>Sleutels roteren</Btn>}
            <Btn icon={RefreshCw} onClick={laad}>Opnieuw controleren</Btn>
          </div>
        </>
      )}
      <div className="foot"><Btn v="p" onClick={() => close()}>Sluiten</Btn></div>
    </>
  );
}

