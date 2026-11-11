import { useState } from 'react'
import { Boxes, Brain, Layers, Plus, Terminal, X, Sparkles, Cpu } from 'lucide-react'
import { api } from '@/lib/api'
import { useAsync } from '@/hooks/useAsync'
import { agentColor, fmtDate } from '@/lib/format'
import { Card, AgentChip } from '@/components/ui/Card'
import { Badge, Button, Callout, EmptyState, Field, Skeleton } from '@/components/ui/Primitives'

export default function Agents() {
  const { data: agents, loading } = useAsync(() => api.listAgents(), [])
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [model, setModel] = useState('')
  const [provider, setProvider] = useState('Google AI')
  const [desc, setDesc] = useState('')
  const [saving, setSaving] = useState(false)

  const register = async () => {
    setSaving(true)
    try {
      await api.registerAgent({
        name: name || 'New agent',
        model: model || 'gemini-2.5-flash',
        model_provider: provider,
        description: desc,
        color_index: 3,
      })
      setShowForm(false)
      setName('')
      setModel('')
      setDesc('')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="page-head page-head-row">
        <div>
          <div className="page-eyebrow">Library</div>
          <h1 className="page-title">Agents</h1>
          <p className="page-desc">
            An agent is more than a model. Bifrost treats <em>model + instructions + tools +
            orchestration + memory</em> as one comparable unit, so a leaderboard row always reflects
            a whole working system.
          </p>
        </div>
        <Button variant="primary" icon={<Plus />} onClick={() => setShowForm(true)}>
          Register agent
        </Button>
      </div>

      <Callout tone="teal" icon={<Brain size={16} style={{ marginTop: 1 }} />}>
        <div>
          <strong>Model ≠ agent.</strong> Swapping Gemini Pro for Flash while keeping the harness
          identical produces a <em>different agent</em> — Bifrost scores them as such, and never
          attributes a result to the model alone.
        </div>
      </Callout>

      {loading ? (
        <div className="grid grid-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} h={250} radius={16} />
          ))}
        </div>
      ) : (
        <div className="grid grid-3">
          {(agents ?? []).map((a) => {
            const color = agentColor(a.color_index)
            return (
              <Card key={a.id} bodyClassName="tight">
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 12,
                      display: 'grid',
                      placeItems: 'center',
                      background: `color-mix(in srgb, ${color} 16%, transparent)`,
                      border: `1px solid color-mix(in srgb, ${color} 34%, transparent)`,
                      color,
                    }}
                  >
                    <Boxes size={19} />
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    <Badge tone="teal" dot>
                      active
                    </Badge>
                    <Badge tone="neutral">sys {a.system_prompt_version}</Badge>
                  </div>
                </div>

                <div className="mt-3">
                  <AgentChip name={a.name} colorIndex={a.color_index} />
                  <div className="tiny muted" style={{ marginTop: 2 }}>
                    registered {fmtDate(a.registered_at)}
                  </div>
                </div>

                <div className="small muted mt-2" style={{ minHeight: 54 }}>
                  {a.description}
                </div>

                <div className="divider mt-3 mb-3" />

                <div className="stack" style={{ gap: 9 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <Cpu size={13} className="muted" style={{ flexShrink: 0 }} />
                    <span className="tiny muted" style={{ width: 76 }}>
                      Model
                    </span>
                    <span className="small strong truncate">{a.model}</span>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <Sparkles size={13} className="muted" style={{ flexShrink: 0 }} />
                    <span className="tiny muted" style={{ width: 76 }}>
                      Provider
                    </span>
                    <span className="small strong truncate">{a.model_provider}</span>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <Layers size={13} className="muted" style={{ flexShrink: 0 }} />
                    <span className="tiny muted" style={{ width: 76 }}>
                      Orchestration
                    </span>
                    <span className="small strong truncate">{a.orchestration}</span>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <Brain size={13} className="muted" style={{ flexShrink: 0 }} />
                    <span className="tiny muted" style={{ width: 76 }}>
                      Memory
                    </span>
                    <span className="small strong truncate">{a.memory}</span>
                  </div>
                </div>

                <div className="mt-3">
                  <div className="tiny muted mb-2">Tool surface</div>
                  <div className="row-wrap" style={{ gap: 5 }}>
                    {a.tools.map((t) => (
                      <span className="badge badge-neutral tip" data-tip={t.description} key={t.name}>
                        <Terminal /> {t.name}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="divider mt-3 mb-2" />
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span className="tiny muted">Pricing / 1k tokens</span>
                  <span className="mono tiny">
                    ${a.cost_per_1k_input.toFixed(4)} in · ${a.cost_per_1k_output.toFixed(4)} out
                  </span>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      <Card title="Anatomy of an agent" subtitle="What the benchmark harness actually controls">
        <div className="grid grid-5" style={{ gap: 14 }}>
          {[
            ['Model', 'The LLM that generates the solution. Swapped freely — but never compared in isolation.'],
            ['Instructions', 'The system prompt template, pinned per run so no agent gets a friendlier brief.'],
            ['Tools', 'The sandbox tool surface. Same tools, same permissions, same sandbox for everyone.'],
            ['Orchestration', 'The control loop — ReAct, plan-act-verify, or a state machine.'],
            ['Memory', 'What persists between steps: scratchpad, vector store, or nothing at all.'],
          ].map(([title, body], i) => (
            <div key={title}>
              <div className="row" style={{ gap: 8, marginBottom: 6 }}>
                <span
                  className="agent-dot"
                  style={{ background: agentColor(i) }}
                />
                <span className="strong" style={{ fontSize: 13 }}>
                  {title}
                </span>
              </div>
              <div className="small muted">{body}</div>
            </div>
          ))}
        </div>
      </Card>

      {showForm && (
        <div className="modal-backdrop" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">Register an agent</div>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setShowForm(false)}>
                <X />
              </button>
            </div>
            <div className="modal-body">
              <div className="stack" style={{ gap: 14 }}>
                <Field label="Agent name">
                  <input
                    className="input"
                    placeholder="e.g. Atlas Coder"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
                <Field label="Model">
                  <input
                    className="input"
                    placeholder="e.g. gemini-2.5-pro"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                </Field>
                <Field label="Model provider">
                  <select
                    className="select"
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                  >
                    <option>Google AI</option>
                    <option>OpenRouter</option>
                    <option>Anthropic</option>
                    <option>OpenAI</option>
                    <option>Local (vLLM)</option>
                  </select>
                </Field>
                <Field label="Description" hint="Shown on the leaderboard and run pages">
                  <textarea
                    className="input"
                    style={{ height: 78, paddingTop: 9, resize: 'vertical' }}
                    placeholder="How does this agent differ from the others?"
                    value={desc}
                    onChange={(e) => setDesc(e.target.value)}
                  />
                </Field>
                <Callout tone="amber">
                  Tools, orchestration and memory are attached by the backend adapter. Registering
                  here defines the identity; the adapter supplies the runtime.
                </Callout>
              </div>
            </div>
            <div className="modal-foot">
              <Button onClick={() => setShowForm(false)}>Cancel</Button>
              <Button variant="primary" loading={saving} onClick={register}>
                Register agent
              </Button>
            </div>
          </div>
        </div>
      )}

      {!loading && (agents ?? []).length === 0 && (
        <Card>
          <EmptyState
            icon={<Boxes size={30} />}
            title="No agents registered"
            description="Register at least one agent to start benchmarking."
            action={
              <Button variant="primary" icon={<Plus />} onClick={() => setShowForm(true)}>
                Register agent
              </Button>
            }
          />
        </Card>
      )}
    </div>
  )
}
