import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeft, ChevronRight, Columns3, CopyIcon, FileOutput, FileText, FolderTree,
  History, Info, ListChecks, PackageCheck, SearchCheck, ShieldCheck, Sparkles,
} from 'lucide-react';
import SelectDocumentsDialog from '../components/SelectDocumentsDialog';
import Spinner from '../components/Spinner';
import { useAiTasksConfig, useCreateAiTask } from '../api/hooks';

const TASKS = [
  {
    value: 'analyze', label: 'Analyze Documents', icon: SearchCheck,
    description: 'Score and rank documents against criteria, with findings and citations. Good for shortlisting resumes against a job description, or scoring proposals against requirements.',
    resultsPreview: "A ranked list of documents with a 0-100 score, key findings that justify each score, anything your criteria call for that a document is missing, and a summary explaining the overall ranking - every claim links back to its source.",
  },
  {
    value: 'compare', label: 'Compare Documents', icon: Columns3,
    description: 'Identify similarities and differences across documents. Good for comparing contract versions, policy revisions, or competing proposals.',
    resultsPreview: "An overall comparison broken down by dimension (e.g. terms, pricing, scope), plus a short write-up of what's distinctive about each individual document - all with source citations.",
  },
  {
    value: 'summarize', label: 'Summarize Documents', icon: FileText,
    description: 'Get a concise summary of each document, and an executive summary across all of them. Good for digesting a large batch of reports or papers quickly.',
    resultsPreview: "A short summary per document, plus one executive summary tying the common themes together when you select more than one document.",
  },
  {
    value: 'extract', label: 'Extract Information', icon: ListChecks,
    description: 'Pull specific fields out of every document into a combined table. Good for turning invoices, forms, or resumes into structured data.',
    resultsPreview: "The fields you asked for (or the most salient ones, if you leave the field list blank) pulled out of every document into one combined table, each value linked back to its source.",
  },
  {
    value: 'validate', label: 'Validate Against Reference Documents', icon: ShieldCheck,
    description: 'Check documents for compliance against a policy or standard you provide as a reference. Good for auditing SOPs, contracts, or submissions against a checklist.',
    resultsPreview: "A compliance score per document, the specific violations and compliant points found against your reference documents, and an overview of how the whole set stacks up.",
  },
  {
    value: 'find_similar', label: 'Find Similar Documents', icon: CopyIcon,
    description: 'Group documents that are semantically similar to each other. Good for spotting duplicate or near-duplicate content in a large library.',
    resultsPreview: "Documents grouped into clusters of near-duplicate or closely related content, each with a short AI-written label explaining what ties that cluster together.",
  },
  {
    value: 'organize', label: 'Organize Documents', icon: FolderTree,
    description: 'Automatically sort documents into labeled groups by topic or theme. Good for making sense of an unsorted upload of mixed content.',
    resultsPreview: "Documents automatically sorted into labeled groups, so you can see how your library naturally breaks down without organizing it by hand.",
  },
  {
    value: 'report', label: 'Generate Reports', icon: FileOutput,
    description: 'Synthesize a structured, multi-section report from a set of documents. Good for turning raw source material into a shareable writeup.',
    resultsPreview: "One structured report with multiple sections, synthesized across every selected document and built around the focus you give it, with citations back to the source documents.",
  },
];

const STEP_LABELS = ['Task', 'Documents', 'Configure', 'Run'];

// Port of templates/ai_tasks/wizard.html's no-run branch (steps 1-4,
// client-side wizard, no server round-trip until Run).
export default function AiTasks() {
  const navigate = useNavigate();
  const { data: config } = useAiTasksConfig();
  const createRun = useCreateAiTask();

  const [currentStep, setCurrentStep] = useState(1);
  const [taskType, setTaskType] = useState(null);
  const [selectedDocs, setSelectedDocs] = useState({});
  const [selectedRefs, setSelectedRefs] = useState({});
  const [taskConfig, setTaskConfig] = useState({ similarity_threshold: 0.85 });
  const [error, setError] = useState('');

  const maxDocuments = config?.max_documents ?? 100;
  const currentTask = TASKS.find((t) => t.value === taskType) || null;
  const needsReference = taskType === 'analyze' || taskType === 'validate';
  const selectedCount = Object.keys(selectedDocs).length;

  const canAdvance = currentStep === 1 ? !!taskType : currentStep === 2 ? selectedCount > 0 && selectedCount <= maxDocuments : true;

  const selectTask = (value) => {
    setTaskType(value);
    setCurrentStep(2);
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      const run = await createRun.mutateAsync({
        task_type: taskType,
        document_ids: Object.keys(selectedDocs).map(Number),
        reference_document_ids: needsReference ? Object.keys(selectedRefs).map(Number) : [],
        config: taskConfig,
      });
      navigate(`/ai-tasks/${run.id}/results`);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">AI Tasks</h1>
          <p className="mt-1 text-sm text-muted dark:text-muted-dark">Select a task, choose your documents, and let the AI do the reviewing.</p>
        </div>
        <button onClick={() => navigate('/ai-tasks/history')} className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
          <History className="h-4 w-4" /> History
        </button>
      </div>

      <div className="mb-6 flex items-center gap-2 text-xs font-medium text-muted dark:text-muted-dark">
        {STEP_LABELS.map((label, index) => (
          <span key={label} className="flex items-center gap-2">
            <span className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] ${currentStep === index + 1 ? 'border-primary bg-primary text-white' : currentStep > index + 1 ? 'border-success bg-success/10 text-success' : 'border-line text-muted dark:border-line-dark'}`}>
              {index + 1}
            </span>
            <span className={currentStep === index + 1 ? 'text-ink dark:text-ink-dark' : ''}>{label}</span>
            {index < STEP_LABELS.length - 1 && <ChevronRight className="h-3 w-3" />}
          </span>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-2.5 text-sm text-danger dark:text-danger-dark">{error}</div>
      )}

      <form onSubmit={onSubmit}>
        {currentStep === 1 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {TASKS.map((task) => (
              <button
                key={task.value} type="button" onClick={() => selectTask(task.value)}
                className={`flex flex-col items-start gap-2 rounded-xl border p-5 text-left shadow-soft transition-all duration-150 hover:-translate-y-0.5 hover:shadow-softer ${taskType === task.value ? 'border-primary bg-primary/5 dark:bg-primary/10' : 'border-line bg-card dark:border-line-dark dark:bg-card-dark'}`}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                  <task.icon className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{task.label}</h3>
                <p className="text-xs text-muted dark:text-muted-dark">{task.description}</p>
              </button>
            ))}
          </div>
        )}

        {currentTask && currentStep > 1 && (
          <div className="mb-6 flex flex-col gap-3 rounded-xl border border-primary/20 bg-primary-soft/30 p-4 dark:border-primary/25 dark:bg-primary/10 sm:flex-row sm:gap-6">
            <div className="flex-1">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary dark:text-primary-soft"><Info className="h-3.5 w-3.5" /> What this task does</p>
              <p className="mt-1 text-sm text-ink dark:text-ink-dark">{currentTask.description}</p>
            </div>
            <div className="flex-1 sm:border-l sm:border-primary/20 sm:pl-6 sm:dark:border-primary/25">
              <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary dark:text-primary-soft"><PackageCheck className="h-3.5 w-3.5" /> What you'll get back</p>
              <p className="mt-1 text-sm text-ink dark:text-ink-dark">{currentTask.resultsPreview}</p>
            </div>
          </div>
        )}

        {currentStep === 2 && (
          <div className="rounded-xl border border-line bg-card p-6 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <h3 className="mb-1 text-sm font-semibold text-ink dark:text-ink-dark">Select Documents</h3>
            <p className="mb-4 text-xs text-muted dark:text-muted-dark">Choose the documents to run "{currentTask?.label}" on.</p>

            <SelectDocumentsDialog selected={selectedDocs} onChange={setSelectedDocs} triggerLabel="Select Documents" />

            {needsReference && (
              <div className="mt-4">
                <h4 className="mb-1 text-sm font-semibold text-ink dark:text-ink-dark">Reference Documents</h4>
                <p className="mb-3 text-xs text-muted dark:text-muted-dark">Documents to check the selected documents against (e.g. a job description, a policy, a standard).</p>
                <SelectDocumentsDialog selected={selectedRefs} onChange={setSelectedRefs} triggerLabel="Select Reference Documents" />
              </div>
            )}

            <p className={`mt-4 text-xs ${selectedCount > maxDocuments ? 'text-danger dark:text-danger-dark' : 'text-muted dark:text-muted-dark'}`}>
              {selectedCount} of {maxDocuments} documents allowed selected.
            </p>
          </div>
        )}

        {currentStep === 3 && (
          <div className="rounded-xl border border-line bg-card p-6 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <h3 className="mb-1 text-sm font-semibold text-ink dark:text-ink-dark">Configure <span className="font-normal text-muted dark:text-muted-dark">(optional)</span></h3>
            <p className="mb-4 text-xs text-muted dark:text-muted-dark">Every field below has a sensible default - skip this step if you're not sure.</p>

            {(taskType === 'analyze' || taskType === 'validate') && (
              <div className="mb-4">
                <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Criteria</label>
                <textarea
                  value={taskConfig.criteria || ''} onChange={(e) => setTaskConfig({ ...taskConfig, criteria: e.target.value })} rows={4}
                  placeholder="e.g. Requires 5+ years of Python experience, a relevant degree, and at least one cloud certification."
                  className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                />
              </div>
            )}

            {taskType === 'extract' && (
              <div className="mb-4">
                <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Fields to extract (comma-separated)</label>
                <input
                  type="text"
                  onChange={(e) => setTaskConfig({ ...taskConfig, fields: e.target.value.split(',').map((f) => f.trim()).filter(Boolean) })}
                  placeholder="e.g. name, date, amount, parties"
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                />
                <p className="mt-1 text-[11px] text-muted dark:text-muted-dark">Leave blank to let the AI infer the most salient fields.</p>
              </div>
            )}

            {taskType === 'summarize' && (
              <div className="mb-4">
                <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Summary length</label>
                <select
                  value={taskConfig.length || '3-5 sentences'} onChange={(e) => setTaskConfig({ ...taskConfig, length: e.target.value })}
                  className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                >
                  <option value="1-2 sentences">Brief (1-2 sentences)</option>
                  <option value="3-5 sentences">Standard (3-5 sentences)</option>
                  <option value="a full paragraph">Detailed (a full paragraph)</option>
                </select>
              </div>
            )}

            {(taskType === 'find_similar' || taskType === 'organize') && (
              <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Similarity threshold</label>
                  <input
                    type="range" min="0.5" max="0.99" step="0.01" value={taskConfig.similarity_threshold ?? 0.85}
                    onChange={(e) => setTaskConfig({ ...taskConfig, similarity_threshold: Number(e.target.value) })}
                    className="w-full"
                  />
                  <p className="mt-1 text-[11px] text-muted dark:text-muted-dark">Higher = only very close matches grouped together. Current: {taskConfig.similarity_threshold ?? 0.85}</p>
                </div>
                {taskType === 'organize' && (
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Target number of groups (optional)</label>
                    <input
                      type="number" min="1" value={taskConfig.target_groups || ''} placeholder="Auto"
                      onChange={(e) => setTaskConfig({ ...taskConfig, target_groups: e.target.value ? Number(e.target.value) : undefined })}
                      className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    />
                  </div>
                )}
              </div>
            )}

            {taskType === 'report' && (
              <div className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Report title</label>
                  <input
                    type="text" value={taskConfig.title || ''} onChange={(e) => setTaskConfig({ ...taskConfig, title: e.target.value })}
                    placeholder="Generated Report"
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Focus</label>
                  <input
                    type="text" value={taskConfig.focus || ''} onChange={(e) => setTaskConfig({ ...taskConfig, focus: e.target.value })}
                    placeholder="e.g. sales trends"
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                  />
                </div>
              </div>
            )}

            {taskType === 'compare' && (
              <p className="text-sm text-muted dark:text-muted-dark">Compare Documents has no additional options - it compares whatever you selected.</p>
            )}
          </div>
        )}

        <div className="mt-6 flex items-center justify-between">
          {currentStep > 1 && (
            <button type="button" onClick={() => setCurrentStep((s) => s - 1)} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
              <ChevronLeft className="h-4 w-4" /> Back
            </button>
          )}
          <div className="ml-auto flex gap-2">
            {currentStep < 4 && (
              <button type="button" onClick={() => canAdvance && setCurrentStep((s) => s + 1)} disabled={!canAdvance} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-50">
                Next <ChevronRight className="h-4 w-4" />
              </button>
            )}
            {currentStep === 4 && (
              <button type="submit" disabled={createRun.isPending || !canAdvance} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-70">
                {createRun.isPending ? <Spinner size={16} /> : <Sparkles className="h-4 w-4" />}
                <span>{createRun.isPending ? 'Starting…' : 'Run AI'}</span>
              </button>
            )}
          </div>
        </div>

        {currentStep === 4 && (
          <div className="mt-6 rounded-xl border border-line bg-surface p-5 text-sm dark:border-line-dark dark:bg-white/5">
            <p className="font-semibold text-ink dark:text-ink-dark">Ready to run</p>
            <p className="mt-1 text-muted dark:text-muted-dark">{currentTask?.label} over {selectedCount} document{selectedCount !== 1 ? 's' : ''}.</p>
          </div>
        )}
      </form>
    </>
  );
}
