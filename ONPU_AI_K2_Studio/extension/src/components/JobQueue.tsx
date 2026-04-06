/**
 * Job queue panel: list active jobs with progress and cancel.
 * Prompt 004 — extension UI.
 */
import React from 'react';

export interface JobItem {
  job_id: string;
  engine_type: string;
  status: string;
  progress?: string;
  created_at: number;
}

interface JobQueueProps {
  jobs: JobItem[];
  onCancel?: (jobId: string) => void;
  onSelectResult?: (jobId: string) => void;
  className?: string;
}

export const JobQueue: React.FC<JobQueueProps> = ({
  jobs,
  onCancel,
  onSelectResult,
  className = '',
}) => {
  const canCancel = (status: string) =>
    status === 'queued' || status === 'running';

  return (
    <div className={`job-queue-panel ${className}`} aria-label="Active jobs">
      <h3>Active jobs</h3>
      {jobs.length === 0 ? (
        <p className="job-queue-empty">No active jobs.</p>
      ) : (
        <ul className="job-queue-list">
          {jobs.map((job) => (
            <li key={job.job_id} className="job-queue-item" data-status={job.status}>
              <div className="job-queue-item-main">
                <span className="job-id">{job.job_id}</span>
                <span className="engine">{job.engine_type}</span>
                <span className="status">{job.status}</span>
                {job.progress && (
                  <span className="progress" title={job.progress}>
                    {job.progress}
                  </span>
                )}
              </div>
              <div className="job-queue-item-actions">
                {job.status === 'complete' && onSelectResult && (
                  <button
                    type="button"
                    onClick={() => onSelectResult(job.job_id)}
                  >
                    Get result
                  </button>
                )}
                {canCancel(job.status) && onCancel && (
                  <button
                    type="button"
                    onClick={() => onCancel(job.job_id)}
                    aria-label={`Cancel job ${job.job_id}`}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default JobQueue;
