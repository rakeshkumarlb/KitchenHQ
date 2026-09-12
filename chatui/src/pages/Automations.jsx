import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, LoaderCircle, PlayCircle, XCircle } from 'lucide-react';
import { kitchenApi } from '../services/api';

// The agent-api /jobs endpoint only returns job names, so the responsible agent,
// task summary and usual cron time are described here for the tiles.
const JOB_META = {
	weekly_menu: {
		label: 'Weekly menu',
		agent: 'Executive Chef',
		description: "Reads current inventory, the chef note and the household's top-rated recipes, then writes and saves a full Monday–Sunday menu.",
		schedule: 'Saturdays, 10:00',
	},
	sunday_prep: {
		label: 'Sunday prep',
		agent: 'Sous Chef',
		description: 'Turns the saved weekly menu into a Sunday batch-prep plan capped at 60 minutes.',
		schedule: 'Sundays, 14:00',
	},
	nightly_prep: {
		label: 'Nightly prep',
		agent: 'Sous Chef',
		description: "Saves a practical 10-minute head-start task for tomorrow's breakfast and lunch.",
		schedule: 'Daily, 20:00',
	},
	morning_cooking: {
		label: 'Morning cooking',
		agent: 'Sous Chef',
		description: "Builds a detailed parallel cooking plan for today's breakfast and lunch, capped at 40 minutes.",
		schedule: 'Weekdays, 06:30',
	},
	dinner_cooking: {
		label: 'Dinner cooking',
		agent: 'Sous Chef',
		description: "Builds a detailed parallel cooking plan for today's snack and dinner, capped at 40 minutes.",
		schedule: 'Weekdays, 18:00',
	},
	pantry_manager: {
		label: 'Pantry manager',
		agent: 'Pantry Manager',
		description: 'Checks stock against the upcoming menu and saves a shopping list proposal. Never changes inventory.',
		schedule: 'Daily, 18:00',
	},
	menu_audit: {
		label: 'Menu audit',
		agent: 'Food Inspector',
		description: "Scores every not-yet-audited weekly menu slot against the household's dietary rules and preferences, with written feedback.",
		schedule: 'Daily, 22:30',
	},
	task_audit: {
		label: 'Task audit',
		agent: 'Food Inspector',
		description: "Scores every not-yet-audited prep task against the same rules and preferences the Sous Chef used, with written feedback.",
		schedule: 'Daily, 22:45',
	},
};

const RECENT_RUN_LIMIT = 10;

const metaFor = (jobName) => JOB_META[jobName] || { label: jobName, agent: 'Agent', description: 'Runs on demand.', schedule: 'On demand' };

function statusIcon(status) {
	if (status === 'completed') return <CheckCircle2 size={15} />;
	if (status === 'failed') return <XCircle size={15} />;
	return <Clock3 size={15} />;
}

export default function Automations() {
	const [jobs, setJobs] = useState([]);
	const [runs, setRuns] = useState([]);
	const [running, setRunning] = useState('');
	const [results, setResults] = useState({});
	const [error, setError] = useState('');

	const load = async () => {
		try {
			setError('');
			const [jobList, runList] = await Promise.all([kitchenApi.listAutomationJobs(), kitchenApi.listAutomationRuns()]);
			setJobs(jobList);
			setRuns(runList);
		} catch (requestError) {
			setError(requestError.message);
		}
	};

	useEffect(() => { load(); }, []);

	const invoke = async (jobName) => {
		setRunning(jobName);
		setError('');
		try {
			const outcome = await kitchenApi.invokeAutomation(jobName);
			setResults((current) => ({ ...current, [jobName]: outcome }));
			await load();
		} catch (requestError) {
			setError(requestError.message);
		} finally {
			setRunning('');
		}
	};

	const recentRuns = runs.slice(0, RECENT_RUN_LIMIT);

	return <div className="page-content">
		<div className="page-lead">
			<div><p className="eyebrow">Autonomous jobs</p><h2>Automa<em>tions.</em></h2><p>Trigger any scheduled job on demand and see exactly what the agent did.</p></div>
		</div>
		{error && <div className="chat-error" role="alert"><span>{error}</span></div>}
		<section className="task-group">
			<h3>Run now</h3>
			<div className="automation-jobs">
				{jobs.map((jobName) => {
					const meta = metaFor(jobName);
					return <article className="automation-job soft-outset" key={jobName}>
						<div className="automation-job-head">
							<b>{meta.label}</b>
							<span className="automation-job-agent">{meta.agent}</span>
						</div>
						<p className="automation-job-desc">{meta.description}</p>
						<p className="automation-job-schedule"><Clock3 size={13} /> {meta.schedule}</p>
						<button type="button" className="secondary-button automation-job-run" disabled={running === jobName} onClick={() => invoke(jobName)}>
							{running === jobName ? <LoaderCircle className="spin" size={15} /> : <PlayCircle size={15} />}
							{running === jobName ? 'Running...' : 'Run now'}
						</button>
						{results[jobName] && <p className="automation-result">{results[jobName].result}</p>}
					</article>;
				})}
				{!jobs.length && <div className="empty-state">No automations registered.</div>}
			</div>
		</section>
		<section className="task-group">
			<h3>Recent runs</h3>
			{recentRuns.length ? recentRuns.map((run) => <article className="automation-run soft-outset" key={run.id}>
				<span className={`automation-status ${run.status}`}>{statusIcon(run.status)} {run.status}</span>
				<div className="automation-run-copy">
					<b>{metaFor(run.job_name).label}</b>
					<small>{run.agent_role} &middot; {run.finished_at}</small>
					<p>{run.status === 'failed' ? run.error : run.result}</p>
				</div>
			</article>) : <div className="empty-state">No automation runs yet.</div>}
		</section>
	</div>;
}
