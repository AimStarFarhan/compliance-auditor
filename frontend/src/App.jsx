import { useEffect, useMemo, useRef, useState } from 'react'
import {
  LayoutDashboard, ShieldCheck, GraduationCap, Database, ArrowUpRight,
  Upload, Sparkles, RefreshCw, FileDown, Check, X, CircleDot, ChevronRight,
  Plus, Zap, Layers, Lock, FileSearch, Cpu,
} from 'lucide-react'
import {
  runAudit, downloadPdf, confirmMapping, rejectMapping,
  fetchCategories, fetchCacheStats, fetchPatterns,
  fetchAiStatus, fetchSamples, fetchSampleFile,
} from './api'
import { StatusPill, SeverityBadge, UnmappedStatusPill, Sparkline } from './components'

const NAV = [
  { id: 'landing', label: 'Home', icon: null, public: true },
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'audit', label: 'Audit Results', icon: ShieldCheck },
  { id: 'training', label: 'Training Lab', icon: GraduationCap },
  { id: 'cache', label: 'Rule Cache', icon: Database },
]

export default function App() {
  const [view, setView] = useState('landing')
  const [file, setFile] = useState(null)
  const [useAi, setUseAi] = useState(true)
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState(null)
  const [categories, setCategories] = useState([])
  const [cacheStats, setCacheStats] = useState(null)
  const [patterns, setPatterns] = useState([])
  const [aiStatus, setAiStatus] = useState(null)
  const [samples, setSamples] = useState([])
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef(null)

  const notify = msg => { setToast(msg); setTimeout(() => setToast(null), 3500) }

  const refreshMeta = () => {
    fetchCategories().then(setCategories).catch(() => {})
    fetchCacheStats().then(setCacheStats).catch(() => {})
    fetchPatterns().then(setPatterns).catch(() => {})
    fetchAiStatus().then(setAiStatus).catch(() => {})
    fetchSamples().then(setSamples).catch(() => {})
  }

  useEffect(refreshMeta, [])

  function startNewAudit() {
    setReport(null)
    setFile(null)
    setError(null)
    setView('dashboard')
  }

  function pickFile(f) {
    setFile(f)
    setReport(null)
    auditFile(f)
  }

  async function auditFile(f) {
    if (!f) return
    setBusy(true); setError(null)
    setView('audit')
    try {
      const r = await runAudit(f, useAi)
      setReport(r)
      notify(`Audit complete — ${r.passed} pass · ${r.failed} fail${r.device_type === 'unknown' ? ` · ${r.unmapped_lines.length} new constructs` : ''}`)
      refreshMeta()
    } catch (e) {
      setError(e.message)
      setView('dashboard')
    } finally {
      setBusy(false)
    }
  }

  async function doAudit() { auditFile(file) }

  async function loadSample(name) {
    try {
      const f = await fetchSampleFile(name)
      pickFile(f)
    } catch (e) {
      setError(e.message)
    }
  }

  async function doPdf() {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const blob = await downloadPdf(file, useAi)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = file.name.replace(/\.[^.]+$/, '') + '_compliance_report.pdf'
      a.click()
      URL.revokeObjectURL(url)
      notify('PDF report downloaded')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleConfirm(rawLine, category) {
    try {
      await confirmMapping(rawLine, category)
      notify(`Cached: "${rawLine.length > 28 ? rawLine.slice(0, 28) + '…' : rawLine}" → ${category}`)
      setReport(prev => prev && ({
        ...prev,
        unmapped_lines: prev.unmapped_lines.map(u =>
          u.raw_line === rawLine ? { ...u, status: 'human_confirmed', suggested_category: category, confidence: 1.0 } : u,
        ),
      }))
      refreshMeta()
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleReject(rawLine, suggested, confidence) {
    try {
      await rejectMapping(rawLine, suggested, confidence)
      notify('Rejected AI suggestion')
      setReport(prev => prev && ({
        ...prev,
        unmapped_lines: prev.unmapped_lines.map(u =>
          u.raw_line === rawLine ? { ...u, status: 'unmapped', suggested_category: null, confidence: null } : u,
        ),
      }))
    } catch (e) {
      setError(e.message)
    }
  }

  const summary = useMemo(() => {
    if (!report) return null
    return {
      score: report.total_rules ? Math.round((report.passed / report.total_rules) * 100) : null,
      highFails: report.findings.filter(f => f.status === 'fail' && f.severity === 'high').length,
    }
  }, [report])

  // ═══════════════ LANDING PAGE ═══════════════
  if (view === 'landing') {
    return (
      <div className="min-h-screen bg-canvas text-ink">
        {/* nav */}
        <nav className="flex items-center justify-between px-8 py-5 sticky top-0 z-50 bg-canvas/80 backdrop-blur-md border-b border-line/60">
          <div className="flex items-center gap-2.5">
            <CircleDot className="size-7 text-ink" strokeWidth={1.4} />
            <span className="font-display font-semibold text-lg tracking-tight">Quantum Forgers</span>
          </div>
          <ul className="hidden md:flex items-center gap-8 text-sm text-ink-soft font-medium">
            <li className="hover:text-ink cursor-pointer transition-colors">Platform</li>
            <li className="hover:text-ink cursor-pointer transition-colors">Learning Loop</li>
            <li className="hover:text-ink cursor-pointer transition-colors">Benchmarks</li>
            <li className="hover:text-ink cursor-pointer transition-colors">Docs</li>
          </ul>
          <button className="pill-btn pill-btn-dark" onClick={() => setView('dashboard')}>
            <span>Launch App</span>
            <span className="pill-icon"><ArrowUpRight className="size-4" /></span>
          </button>
        </nav>

        {/* hero */}
        <section className="shell mx-3 md:mx-5 my-4 md:my-6 min-h-[80vh] flex flex-col items-center justify-center text-center px-6 py-24 relative overflow-hidden">
          <ShieldCheck className="absolute -bottom-10 -left-10 size-96 text-ink opacity-[0.025] pointer-events-none" strokeWidth={0.8} />
          <div className="mx-auto mb-6 flex w-fit items-center gap-2 rounded-full border border-ink/10 bg-white px-4 py-2 shadow-[0_8px_30px_rgb(31_58_95/0.06)]">
            <Sparkles className="size-4 text-ink" />
            <span className="text-sm font-medium text-ink">SIH26155 · AI-Augmented Network Compliance</span>
          </div>
          <h1 className="font-display text-4xl sm:text-5xl md:text-7xl font-semibold leading-[1.02] max-w-4xl">
            Audit any network config.<br />
            <span className="text-ink-soft">Teach it vendors it's</span> never seen.
          </h1>
          <p className="mt-6 max-w-xl text-base md:text-lg text-ink-soft leading-relaxed">
            CIS-benchmark compliance for Cisco, Juniper and beyond — with a human-confirmed
            learning loop that recognizes new vendor syntaxes live, without code changes or redeploys.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button className="pill-btn pill-btn-dark !py-3 !px-7 text-base" onClick={() => setView('dashboard')}>
              <span>Run Your First Audit</span>
              <span className="pill-icon"><ArrowUpRight className="size-5" /></span>
            </button>
            <button className="pill-btn bg-ink text-white" onClick={() => { setView('dashboard'); loadSample('unknown_vendor_sample.cfg') }}>
              <span>Watch It Learn a New Vendor</span>
              <span className="pill-icon bg-white/20"><Zap className="size-4" /></span>
            </button>
          </div>

          {/* metric strip */}
          <dl className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-y-8">
            <HeroStat value="2" label="Vendors built-in" />
            <HeroStat value="22+" label="CIS benchmark rules" />
            <HeroStat value="Live" label="Vendor learning loop" />
            <HeroStat value="0" label="Code changes to onboard" />
          </dl>
        </section>

        {/* features */}
        <section className="mx-3 md:mx-5 my-6 px-4 md:px-12 py-12">
          <h2 className="font-display text-3xl md:text-4xl font-semibold max-w-lg leading-tight mb-10">
            Architected for real multi-vendor networks
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <FeatureCard
              icon={Layers} title="Vendor-agnostic schema" rowSpan
              desc="One normalized model for firewall, router and switch semantics — Cisco IOS and Juniper SRX built in, more learned live. Lineage is preserved end-to-end for auditability."
            />
            <FeatureCard
              icon={Cpu} title="AI suggestions, human verdicts"
              desc="A local LLM proposes categories for unrecognized constructs. Advisory only — every verdict is human-confirmed."
            />
            <FeatureCard
              icon={FileSearch} title="Instant CIS audit"
              desc="22+ hand-encoded benchmark rules with exact remediation CLI. Advisory text only — the tool never touches your devices."
            />
            <FeatureCard
              icon={Lock} title="Auditability built-in"
              desc="AI-influenced findings are flagged in every report. Confirmed patterns live in an inspectable SQLite cache."
            />
          </div>
        </section>

        {/* CTA */}
        <section className="mx-3 md:mx-5 my-6">
          <div className="relative overflow-hidden rounded-[2rem] md:rounded-[3rem] bg-ink text-white p-12 md:p-24 text-center">
            <GraduationCap className="watermark size-80" strokeWidth={0.8} />
            <h2 className="font-display text-3xl md:text-5xl font-semibold leading-tight relative">
              A judge-proof demo in 60 seconds.
            </h2>
            <p className="mt-4 text-sm md:text-base text-white/70 max-w-md mx-auto relative">
              Upload a config from a vendor the tool has never seen. Confirm the AI's suggestions once —
              every future audit understands it. Live, no engineering ticket.
            </p>
            <button className="pill-btn pill-btn-white !py-2.5 !px-7 mt-8 relative mx-auto" onClick={() => { setView('dashboard'); loadSample('unknown_vendor_sample.cfg') }}>
              <span>See the learning loop</span>
              <span className="pill-icon"><ArrowUpRight className="size-4" /></span>
            </button>
          </div>
        </section>

        {/* footer */}
        <footer className="border-t border-line bg-white/40">
          <div className="max-w-6xl mx-auto px-8 py-14 flex flex-col md:flex-row justify-between gap-10">
            <div className="max-w-xs">
              <div className="flex items-center gap-2.5">
                <CircleDot className="size-6 text-ink" strokeWidth={1.4} />
                <span className="font-display font-semibold">Quantum Forgers</span>
              </div>
              <p className="mt-4 text-sm text-ink-soft leading-relaxed">
                Vendor-agnostic network configuration compliance auditing with a human-confirmed learning loop.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-10 text-sm">
              <FooterCol title="Platform" items={['Dashboard', 'Audit', 'Training Lab', 'Rule Cache']} onNav={setView} />
              <FooterCol title="Resources" items={['README', 'Architecture', 'CIS Benchmarks', 'API Docs']} />
              <FooterCol title="Compliance" items={['Advisory only', 'No device polling', 'No auto-remediation']} />
            </div>
          </div>
          <div className="border-t border-line py-6 text-center text-xs text-ink-faint">
            © 2026 Quantum Forgers · SIH26155 prototype · File upload only — the tool never touches your network
          </div>
        </footer>
      </div>
    )
  }

  // ═══════════════ APP SHELL ═══════════════
  return (
    <div className="min-h-screen bg-canvas text-ink flex">
      {/* ─── Sidebar ─── */}
      <aside className="w-64 shrink-0 bg-white/60 border-r border-line flex flex-col">
        <div className="px-5 py-6 cursor-pointer" onClick={() => setView('landing')}>
          <div className="flex items-center gap-2.5">
            <CircleDot className="size-9 text-ink" strokeWidth={1.2} />
            <div>
              <div className="font-display font-semibold text-base leading-tight">Quantum Forgers</div>
              <div className="text-[10px] text-ink-soft uppercase tracking-wider font-medium">Compliance Auditor</div>
            </div>
          </div>
        </div>

        {/* New Audit — always available */}
        <div className="px-3 pb-2">
          <button onClick={startNewAudit}
            className="w-full flex items-center gap-2.5 bg-ink text-white rounded-full py-3 px-5 text-sm font-semibold shadow-[0_8px_30px_rgb(31_58_95/0.2)] hover:bg-[#2A4A73] transition">
            <Plus className="size-4.5" /> New Audit
          </button>
        </div>

        <nav className="px-3 space-y-1 flex-1">
          {NAV.filter(n => n.icon).map(n => (
            <button
              key={n.id}
              onClick={() => setView(n.id)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-full text-sm font-medium transition ${view === n.id ? 'bg-ink text-white shadow-[0_8px_30px_rgb(31_58_95/0.15)]' : 'text-ink-soft hover:text-ink hover:bg-veil'}`}
            >
              <n.icon className="size-4.5" strokeWidth={2} /> {n.label}
              {n.id === 'training' && report && report.unmapped_lines.length > 0 && (
                <span className={`ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full ${view === n.id ? 'bg-white/20 text-white' : 'bg-ink text-white'}`}>
                  {report.unmapped_lines.length}
                </span>
              )}
              {n.id === 'cache' && cacheStats && cacheStats.total_patterns > 0 && (
                <span className="ml-auto bg-veil-deep text-ink text-[10px] font-bold px-2 py-0.5 rounded-full">
                  {cacheStats.total_patterns}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* LM Studio status */}
        <div className="mx-4 mb-4 rounded-2xl border border-line bg-white p-4">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${aiStatus?.online ? 'bg-emerald-500' : 'bg-ink-faint'}`} />
            <span className="text-xs font-medium">LM Studio</span>
            <span className={`ml-auto text-[11px] font-semibold ${aiStatus?.online ? 'text-emerald-600' : 'text-ink-faint'}`}>
              {aiStatus?.online ? 'online' : 'offline'}
            </span>
          </div>
          {aiStatus?.online && (
            <div className="mt-1.5 text-[10px] text-ink-faint truncate">
              {aiStatus.models?.[0] || 'no model loaded'}
            </div>
          )}
        </div>
      </aside>

      {/* ─── Main ─── */}
      <div className="flex-1 min-w-0 relative">
        {toast && (
          <div className="absolute top-4 right-4 z-50 bg-ink text-white px-5 py-3 rounded-2xl text-sm shadow-[0_8px_30px_rgb(31_58_95/0.25)]">
            {toast}
          </div>
        )}

        <header className="h-16 border-b border-line bg-canvas/80 backdrop-blur-md flex items-center px-8 gap-3 sticky top-0 z-40">
          <h1 className="font-display text-lg font-semibold">
            {NAV.find(n => n.id === view)?.label}
          </h1>
          <div className="ml-auto flex items-center gap-2 flex-wrap">
            {file && !busy && (
              <span className="text-xs text-ink-soft bg-white border border-line rounded-full px-3 py-1.5 font-mono max-w-48 truncate">
                {file.name}
              </span>
            )}
            {busy && (
              <span className="text-xs text-ink-soft flex items-center gap-2 bg-white border border-line rounded-full px-3 py-1.5">
                <RefreshCw className="size-3.5 animate-spin" /> Auditing…
              </span>
            )}
            <label className="flex items-center gap-2 text-xs font-medium text-ink-soft cursor-pointer select-none bg-white border border-line rounded-full px-4 py-1.5">
              <input type="checkbox" checked={useAi} onChange={e => setUseAi(e.target.checked)} className="accent-ink" />
              AI suggestions
            </label>
            {report && (
              <>
                <button className="pill-btn pill-btn-outline" onClick={doAudit} disabled={busy}>
                  <RefreshCw className="size-4" /> Re-run
                </button>
                <button className="pill-btn pill-btn-dark" onClick={doPdf} disabled={busy}>
                  <span>PDF Report</span>
                  <span className="pill-icon"><FileDown className="size-4" /></span>
                </button>
              </>
            )}
          </div>
        </header>

        <main className="p-5 md:p-8 max-w-6xl mx-auto space-y-6">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 rounded-3xl p-5 text-sm flex items-start gap-3">
              <X className="size-5 mt-0.5 shrink-0" /> {error}
            </div>
          )}

          {/* ═══ DASHBOARD ═══ */}
          {view === 'dashboard' && (
            <>
              <section
                className={`shell p-12 md:p-16 text-center relative overflow-hidden transition ${dragOver ? 'ring-4 ring-ink/15' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files[0]) pickFile(e.dataTransfer.files[0]) }}
              >
                <Upload className="absolute -bottom-8 -left-8 size-64 text-ink opacity-[0.03] pointer-events-none" strokeWidth={1} />
                <div className="relative">
                  <div className="mx-auto mb-5 flex size-16 items-center justify-center rounded-full bg-white border border-line shadow-[0_8px_30px_rgb(31_58_95/0.06)]">
                    <ShieldCheck className="size-7 text-ink" strokeWidth={1.6} />
                  </div>
                  <h2 className="font-display text-3xl md:text-4xl font-semibold leading-tight">
                    {file && !report && !busy ? 'Ready for the next audit' : 'From config chaos to compliance clarity'}
                  </h2>
                  <p className="mt-3 text-sm md:text-base text-ink-soft max-w-md mx-auto leading-relaxed">
                    Upload any network device configuration — known vendor or not. Unknown syntaxes enter the learning loop automatically.
                  </p>
                  <div className="mt-7 flex items-center justify-center gap-3">
                    <button className="pill-btn pill-btn-dark !py-2.5 !px-6" onClick={() => inputRef.current?.click()}>
                      <span>Choose file</span>
                      <span className="pill-icon"><ArrowUpRight className="size-4" /></span>
                    </button>
                    <span className="text-ink-faint text-xs">or drag &amp; drop .cfg / .txt</span>
                  </div>
                  <input ref={inputRef} type="file" accept=".cfg,.txt,.conf" className="hidden"
                    onChange={e => e.target.files[0] && pickFile(e.target.files[0])} />
                </div>
              </section>

              <section>
                <h3 className="text-xs font-semibold text-ink-soft uppercase tracking-wider mb-3 px-1">Try a sample configuration</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {samples.map(s => (
                    <button key={s.name} onClick={() => loadSample(s.name)}
                      className="group relative overflow-hidden card-hover text-left bg-white border border-line rounded-[2rem] p-6">
                      <Sparkles className="watermark size-36" strokeWidth={1.5} />
                      <div className="font-mono text-xs text-ink-soft relative">{s.name}</div>
                      <div className="text-sm font-medium mt-2 leading-relaxed relative">{s.description}</div>
                      <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium">
                        Run audit <ChevronRight className="size-3.5 transition-transform group-hover:translate-x-1" />
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            </>
          )}

          {/* ═══ AUDIT ═══ */}
          {view === 'audit' && (
            report ? (
              <AuditReportView report={report} summary={summary} onRerun={doAudit} onPdf={doPdf} busy={busy} onTraining={() => setView('training')} onNew={startNewAudit} />
            ) : busy ? (
              <div className="shell text-center py-24">
                <RefreshCw className="size-8 mx-auto mb-4 text-ink-faint animate-spin" />
                <p className="text-sm text-ink-soft">Auditing {file?.name}…</p>
              </div>
            ) : (
              <EmptyState text="Load a configuration from the Dashboard — or start a New Audit" onBack={() => setView('dashboard')} />
            )
          )}

          {/* ═══ TRAINING LAB ═══ */}
          {view === 'training' && (
            report ? (
              <TrainingLab report={report} categories={categories} onConfirm={handleConfirm} onReject={handleReject} onRerun={doAudit} busy={busy} />
            ) : (
              <EmptyState text="Run an audit first — unmapped lines appear here for the learning loop" onBack={() => setView('dashboard')} />
            )
          )}

          {/* ═══ RULE CACHE ═══ */}
          {view === 'cache' && (
            <>
              <section className="shell p-6 md:p-10">
                <dl className="grid grid-cols-3">
                  <Metric label="Confirmed patterns" value={cacheStats?.total_patterns ?? '—'} big />
                  <Metric label="Categories in use" value={Object.keys(cacheStats?.by_category ?? {}).length} />
                  <Metric label="Vendor knowledge" value={patterns.length ? 'extending…' : '—'} />
                </dl>
              </section>
              <section className="group relative overflow-hidden bg-white border border-line rounded-[2rem]">
                <Database className="watermark size-40" strokeWidth={1.2} />
                <h3 className="font-display font-semibold px-6 py-4 border-b border-line text-sm relative">Human-confirmed command patterns</h3>
                {patterns.length === 0 ? (
                  <p className="px-6 py-8 text-sm text-ink-soft relative">Nothing learned yet. Confirm an unmapped line in the Training Lab and it will appear here.</p>
                ) : (
                  <div className="overflow-x-auto relative">
                    <table className="w-full text-sm">
                      <thead className="text-[11px] uppercase tracking-wide text-ink-faint text-left">
                        <tr className="border-b border-line">
                          <th className="px-6 py-3 font-semibold">Pattern</th><th className="px-4 py-3 font-semibold">Category</th>
                          <th className="px-4 py-3 font-semibold">Example line</th><th className="px-4 py-3 font-semibold">By</th>
                        </tr>
                      </thead>
                      <tbody>
                        {patterns.map((p, i) => (
                          <tr key={i} className="border-b border-line/50 hover:bg-veil/50 transition">
                            <td className="px-6 py-3 font-mono text-xs">{p.pattern}</td>
                            <td className="px-4 py-3"><span className="text-xs bg-veil px-2.5 py-1 rounded-full font-medium">{p.category}</span></td>
                            <td className="px-4 py-3 font-mono text-xs text-ink-soft">{p.example_line}</td>
                            <td className="px-4 py-3 text-xs text-ink-faint">{p.confirmed_by}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </main>

        <footer className="max-w-6xl mx-auto px-8 pb-10 pt-2 text-[11px] text-ink-faint flex gap-4 flex-wrap">
          <span>File upload only — no live device polling</span>
          <span>·</span>
          <span>No auto-remediation — remediation CLI is advisory</span>
          <span>·</span>
          <span>Extensible to new vendors via human-in-the-loop mapping</span>
        </footer>
      </div>
    </div>
  )
}

/* ── Landing helpers ── */
function HeroStat({ value, label }) {
  return (
    <div className="flex flex-col gap-1 px-8">
      <dt className="font-display text-3xl md:text-4xl font-semibold tabular-nums">{value}</dt>
      <dd className="text-sm text-ink-soft">{label}</dd>
    </div>
  )
}

function FeatureCard({ icon: Icon, title, desc, rowSpan }) {
  return (
    <div className={`group relative overflow-hidden card-hover bg-white border border-line rounded-[2rem] p-7 md:p-9 flex flex-col justify-between min-h-56 ${rowSpan ? 'md:row-span-2' : ''}`}>
      <Icon className="watermark size-48" strokeWidth={1} />
      <span className="relative flex size-12 items-center justify-center rounded-2xl bg-veil text-ink">
        <Icon className="size-6" />
      </span>
      <div className="relative mt-6">
        <h3 className={`font-display font-semibold ${rowSpan ? 'text-2xl md:text-3xl' : 'text-xl'}`}>{title}</h3>
        <p className="mt-2 text-sm text-ink-soft leading-relaxed">{desc}</p>
      </div>
    </div>
  )
}

function FooterCol({ title, items, onNav }) {
  return (
    <div>
      <h4 className="text-sm font-semibold">{title}</h4>
      <ul className="mt-3 flex flex-col gap-2.5">
        {items.map((it, i) => (
          <li key={it}>
            <button
              className="text-sm text-ink-soft hover:text-ink transition-colors text-left"
              onClick={() => onNav && ['dashboard', 'audit', 'training', 'cache'].includes(it.toLowerCase().replace(' ', '')) ? onNav(['dashboard', 'audit', 'training', 'cache'][i] || 'dashboard') : onNav?.('dashboard')}
            >
              {it}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ── App helpers ── */
function Metric({ label, value, big }) {
  return (
    <div className="flex flex-col gap-1.5 p-5 md:p-6">
      <dt className={`font-display font-semibold tracking-tight tabular-nums ${big ? 'text-4xl md:text-5xl' : 'text-3xl md:text-4xl'}`}>{value}</dt>
      <dd className="text-sm text-ink-soft">{label}</dd>
    </div>
  )
}

function EmptyState({ text, onBack }) {
  return (
    <div className="shell text-center py-20">
      <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-full bg-white border border-line">
        <CircleDot className="size-6 text-ink-faint" />
      </div>
      <p className="text-sm text-ink-soft mb-4">{text}</p>
      {onBack && <button onClick={onBack} className="pill-btn pill-btn-outline mx-auto">← Dashboard</button>}
    </div>
  )
}

function AuditReportView({ report, summary, onRerun, onPdf, busy, onTraining, onNew }) {
  const isUnknown = report.device_type === 'unknown'
  return (
    <>
      {isUnknown ? (
        /* Unknown vendor — teaching mode banner */
        <section className="group relative overflow-hidden bg-ink text-white rounded-[2rem] p-8">
          <GraduationCap className="watermark size-56" strokeWidth={1} />
          <div className="relative flex flex-wrap items-center gap-6 justify-between">
            <div className="max-w-xl">
              <div className="flex items-center gap-2 mb-3">
                <Zap className="size-5 text-amber-300" />
                <span className="text-xs font-semibold uppercase tracking-wider text-amber-300">New vendor detected — teaching mode</span>
              </div>
              <h2 className="font-display font-semibold text-2xl md:text-3xl leading-tight">
                {report.source_file} is a format we've never seen.
              </h2>
              <p className="text-sm text-white/70 mt-2 leading-relaxed">
                {report.unmapped_lines.length} constructs are ready for the learning loop. The AI has suggested categories —
                confirm a few and re-run: this vendor's syntax will be recognized from now on. No code, no ticket.
              </p>
            </div>
            <div className="flex gap-2.5">
              <button className="pill-btn pill-btn-white" onClick={onTraining}>
                <span>Open Training Lab</span>
                <span className="pill-icon"><ArrowUpRight className="size-4" /></span>
              </button>
              <button className="pill-btn bg-white/10 border border-white/20 text-white hover:bg-white/20 backdrop-blur-md" onClick={onNew}>
                <Plus className="size-4" /> New Audit
              </button>
            </div>
          </div>
        </section>
      ) : (
        <>
          {/* metrics */}
          <section className="shell p-6 md:p-10">
            <dl className="grid grid-cols-2 md:grid-cols-5">
              <Metric label="Compliance" value={`${summary.score}%`} big />
              <Metric label="Rules passed" value={report.passed} />
              <Metric label="Failed" value={report.failed} />
              <Metric label="High severity" value={summary.highFails} />
              <Metric label="Unmapped" value={report.unmapped_lines.length} />
            </dl>
          </section>

          {/* donut + top failures */}
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white card-hover border border-line rounded-[2rem] p-6 flex items-center gap-6">
              <div className="relative">
                <Sparkline pass={report.passed} fail={report.failed} review={report.needs_review} size={110} />
                <div className="absolute inset-0 flex items-center justify-center text-xl font-display font-semibold">
                  {summary.score}%
                </div>
              </div>
              <div className="space-y-2 text-xs text-ink-soft">
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-600" /> Pass · {report.passed}</div>
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm bg-red-600" /> Fail · {report.failed}</div>
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm bg-amber-500" /> Review · {report.needs_review}</div>
              </div>
            </div>
            <div className="group relative overflow-hidden bg-white card-hover border border-line rounded-[2rem] p-6 md:col-span-2">
              <ShieldCheck className="watermark size-44" strokeWidth={1.2} />
              <h4 className="text-xs font-semibold text-ink-soft uppercase tracking-wider mb-4 relative">Top failures</h4>
              <div className="relative">
                {report.findings.filter(f => f.status === 'fail').slice(0, 5).map(f => (
                  <div key={f.rule_id} className="flex items-center gap-3 py-2 border-b border-line/60 last:border-0">
                    <SeverityBadge severity={f.severity} />
                    <span className="font-mono text-[11px] text-ink-faint">{f.rule_id}</span>
                    <span className="text-xs font-medium truncate flex-1">{f.cis_section}</span>
                    <code className="text-[11px] text-ink-soft font-mono hidden lg:inline">{f.remediation_cli}</code>
                  </div>
                ))}
                {report.failed === 0 && <p className="text-sm text-emerald-600 font-medium">No failures — device is fully compliant.</p>}
              </div>
            </div>
          </section>
        </>
      )}

      {/* device meta + actions */}
      <section className="bg-white card-hover border border-line rounded-[2rem] p-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="font-display font-semibold text-lg">{report.source_file}</div>
          <div className="text-xs text-ink-soft mt-1">
            {report.device_type} · {report.hostname || 'no hostname'} · {report.total_rules > 0 ? `${report.total_rules} rules evaluated` : 'no rules for this vendor yet — teach it first'}
          </div>
        </div>
        <div className="flex gap-2.5 flex-wrap">
          <button className="pill-btn pill-btn-outline" onClick={onNew}>
            <Plus className="size-4" /> New Audit
          </button>
          <button className="pill-btn pill-btn-outline" onClick={onRerun} disabled={busy}>
            <RefreshCw className={`size-4 ${busy ? 'animate-spin' : ''}`} /> Re-run Audit
          </button>
          <button className="pill-btn pill-btn-dark" onClick={onPdf} disabled={busy}>
            <span>PDF Report</span>
            <span className="pill-icon"><ArrowUpRight className="size-4" /></span>
          </button>
        </div>
      </section>

      {/* CTA to training */}
      {report.unmapped_lines.length > 0 && (
        <button onClick={onTraining}
          className="group w-full bg-white card-hover border border-line rounded-[2rem] p-5 text-left flex items-center gap-4">
          <span className="flex size-12 items-center justify-center rounded-full bg-veil transition-transform duration-300 group-hover:scale-110">
            <GraduationCap className="size-6" />
          </span>
          <div className="flex-1">
            <div className="text-sm font-semibold">
              {report.unmapped_lines.length} unmapped constructs waiting for review
            </div>
            <div className="text-xs text-ink-soft mt-0.5">Open the Training Lab — confirm or reject AI suggestions in one click.</div>
          </div>
          <ChevronRight className="size-5 transition-transform group-hover:translate-x-1" />
        </button>
      )}

      {/* findings (known vendors) */}
      {!isUnknown && <FindingsTable report={report} />}
      {isUnknown && report.unmapped_lines.length > 0 && (
        <section className="bg-white border border-line rounded-[2rem] p-6">
          <h3 className="font-display font-semibold text-sm mb-4">Constructs detected in {report.source_file}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {report.unmapped_lines.slice(0, 10).map((u, i) => (
              <code key={i} className="text-xs bg-veil border border-line px-3 py-2 rounded-full truncate">{u.raw_line}</code>
            ))}
          </div>
          {report.unmapped_lines.length > 10 && (
            <p className="text-xs text-ink-faint mt-3">+{report.unmapped_lines.length - 10} more — see them all in the Training Lab</p>
          )}
        </section>
      )}
    </>
  )
}

function FindingsTable({ report }) {
  const [filter, setFilter] = useState('all')
  const [sevFilter, setSevFilter] = useState('all')
  const findings = report.findings.filter(f =>
    (filter === 'all' || f.status === filter) && (sevFilter === 'all' || f.severity === sevFilter)
  )
  return (
    <section className="group relative overflow-hidden bg-white border border-line rounded-[2rem]">
      <ShieldCheck className="watermark size-44" strokeWidth={1.2} />
      <div className="relative flex items-center gap-2 px-6 py-4 border-b border-line flex-wrap">
        <h3 className="font-display font-semibold text-sm flex-1">Findings — {report.source_file}</h3>
        {['all', 'fail', 'pass', 'needs_review'].map(s => (
          <button key={s} onClick={() => setFilter(s)}
            className={`text-[11px] px-3 py-1.5 rounded-full border font-semibold transition ${filter === s ? 'bg-ink text-white border-ink' : 'text-ink-soft border-line hover:bg-veil'}`}>
            {s.replace('_', ' ')}
          </button>
        ))}
        <select value={sevFilter} onChange={e => setSevFilter(e.target.value)}
          className="bg-white border border-line text-xs rounded-full px-3 py-1.5 text-ink-soft">
          <option value="all">all severity</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
      </div>
      <div className="relative overflow-x-auto max-h-[70vh] overflow-y-auto rounded-b-[2rem]">
        <table className="w-full text-sm">
          <thead className="bg-veil/60 text-left text-[10px] uppercase tracking-wide text-ink-soft sticky top-0">
            <tr>
              <th className="px-6 py-3 font-semibold">Rule</th><th className="px-4 py-3 font-semibold">CIS Section</th>
              <th className="px-4 py-3 font-semibold">Status</th><th className="px-4 py-3 font-semibold">Sev</th>
              <th className="px-4 py-3 font-semibold">Evidence</th><th className="px-4 py-3 font-semibold">Remediation</th>
            </tr>
          </thead>
          <tbody>
            {findings.map(f => (
              <tr key={f.rule_id} className="border-t border-line/50 hover:bg-veil/40 align-top transition">
                <td className="px-6 py-3 font-mono text-xs text-ink-soft">{f.rule_id}</td>
                <td className="px-4 py-3 max-w-64 font-medium">{f.cis_section}</td>
                <td className="px-4 py-3"><StatusPill status={f.status} /></td>
                <td className="px-4 py-3"><SeverityBadge severity={f.severity} /></td>
                <td className="px-4 py-3 text-xs text-ink-soft max-w-56">{f.evidence}</td>
                <td className="px-4 py-3 font-mono text-xs">{f.remediation_cli}</td>
              </tr>
            ))}
            {findings.length === 0 && (
              <tr><td colSpan="6" className="px-6 py-10 text-center text-sm text-ink-soft">No findings match the filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function TrainingLab({ report, categories, onConfirm, onReject, onRerun, busy }) {
  return (
    <>
      <section className="group relative overflow-hidden bg-ink text-white rounded-[2rem] p-8">
        <GraduationCap className="watermark size-56" strokeWidth={1} />
        <h3 className="font-display font-semibold text-xl relative">Human-in-the-Loop Learning</h3>
        <p className="text-xs text-white/70 mt-2 max-w-2xl relative leading-relaxed">
          The AI suggests a category for each unrecognized construct — <strong className="text-white">advisory only, never a verdict</strong>.
          Your confirmation is cached as a pattern (e.g. <code className="bg-white/10 px-1.5 py-0.5 rounded">ntp server #</code>) and instantly
          resolves the same construct in every future audit. No code changes, no redeploys.
        </p>
      </section>

      {report.unmapped_lines.length === 0 ? (
        <div className="bg-white border border-line rounded-[2rem] p-10 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-full bg-emerald-50 border border-emerald-200">
            <Check className="size-6 text-emerald-600" />
          </div>
          <p className="text-sm text-emerald-700 font-semibold">No unmapped constructs</p>
          <p className="text-xs text-ink-soft mt-1">Every line in this config was recognized.</p>
        </div>
      ) : (
        <section className="bg-white border border-line rounded-[2rem] overflow-hidden">
          <h3 className="font-display font-semibold px-6 py-4 border-b border-line text-sm">
            Unmapped lines · {report.unmapped_lines.length}
          </h3>
          <ul className="divide-y divide-line/50 max-h-[62vh] overflow-y-auto">
            {report.unmapped_lines.map((u, i) => (
              <li key={i} className="px-6 py-4 flex flex-col gap-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-[10px] text-ink-faint font-mono w-8">L{u.line_number}</span>
                  <code className="text-xs bg-veil border border-line px-3 py-1.5 rounded-full">{u.raw_line}</code>
                  <UnmappedStatusPill status={u.status} />
                  {u.status === 'ai_suggested' && (
                    <span className="text-xs text-ink-soft">
                      AI: <strong className="text-ink">{u.suggested_category}</strong>
                      {u.confidence != null && <span className="text-ink-faint"> ({Math.round(u.confidence * 100)}%)</span>}
                    </span>
                  )}
                  {u.status === 'human_confirmed' && (
                    <span className="text-xs text-emerald-700">
                      → <strong>{u.suggested_category}</strong>
                      <span className="text-ink-faint"> {u.suggested_by_ai ? '(AI-suggested, then confirmed)' : '(cached pattern)'}</span>
                    </span>
                  )}
                </div>
                {u.status !== 'human_confirmed' && (
                  <div className="flex items-center gap-2.5 flex-wrap pl-11">
                    <select defaultValue={u.suggested_category || ''}
                      className="text-xs bg-white border border-line rounded-full px-4 py-2 min-w-48">
                      <option value="">— choose category —</option>
                      {categories.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <button
                      className="pill-btn pill-btn-dark !py-2 !px-5 text-xs"
                      onClick={e => {
                        const sel = e.target.closest('li').querySelector('select')
                        if (sel.value) onConfirm(u.raw_line, sel.value)
                      }}>
                      <span>Confirm &amp; Cache</span>
                      <span className="pill-icon"><Check className="size-4" /></span>
                    </button>
                    {u.status === 'ai_suggested' && (
                      <button
                        className="pill-btn bg-red-50 border border-red-200 text-red-700 hover:bg-red-100 !py-2 !px-5 text-xs"
                        onClick={() => onReject(u.raw_line, u.suggested_category, u.confidence)}>
                        <X className="size-4" /> Reject AI
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <div className="px-6 py-4 border-t border-line bg-veil/30">
            <button className="pill-btn pill-btn-dark" onClick={onRerun} disabled={busy}>
              <RefreshCw className={`size-4 ${busy ? 'animate-spin' : ''}`} />
              <span>Re-run Audit — watch what you taught apply live</span>
            </button>
          </div>
        </section>
      )}
    </>
  )
}
