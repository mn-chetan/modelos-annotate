import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NewProjectPage } from './NewProject';

const calls = vi.hoisted(() => ({ create: vi.fn(), upload: vi.fn(), navigate: vi.fn() }));
vi.mock('../../../services/api', () => ({ api: { uploadAssets: (...args: unknown[]) => calls.upload(...args) } }));
vi.mock('../../store', () => ({ request: (...args: unknown[]) => calls.create(...args), refreshProjects: vi.fn(async () => {}) }));
vi.mock('../../router', () => ({ navigate: (...args: unknown[]) => calls.navigate(...args) }));

beforeEach(() => {
  calls.create.mockResolvedValue({ id: 'created-project' });
  URL.createObjectURL = vi.fn(() => '/preview');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it('retries only the uploads that failed, against the one project it created', async () => {
  let failed = false;
  calls.upload.mockImplementation(async (_id: string, files: File[]) => {
    if (files[0].name === 'second.jpg' && !failed) {
      failed = true;
      throw new Error('Upload disconnected');
    }
    return [];
  });
  const { container } = render(<NewProjectPage />);
  fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Traffic review' } });
  const files = [new File(['a'], 'first.jpg', { type: 'image/jpeg' }), new File(['b'], 'second.jpg', { type: 'image/jpeg' })];
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files } });
  fireEvent.click(screen.getByRole('button', { name: 'Create project' }));

  await screen.findByRole('alert');
  expect(screen.getByRole('button', { name: 'Open the saved project' })).toBeTruthy();
  expect(calls.create).toHaveBeenCalledTimes(1);
  const payload = JSON.parse(calls.create.mock.calls[0][1].body);
  expect(payload).toMatchObject({ modality: 'image', task_type: 'object_detection', confidence_threshold: 0.7 });
  expect(payload.quality_policy).toMatchObject({ auto_approve_threshold: 0.7, sample_rate: 0.1 });
  expect(payload.label_ontology[0]).toMatchObject({ name: 'car', color: '#2A78D6' });

  fireEvent.click(screen.getByRole('button', { name: 'Retry remaining uploads' }));
  await waitFor(() => expect(calls.navigate).toHaveBeenCalledWith({ id: 'project', projectId: 'created-project', tab: 'ai' }));
  expect(calls.create).toHaveBeenCalledTimes(1);
  expect(calls.upload.mock.calls.map((c) => c[1][0].name)).toEqual(['first.jpg', 'second.jpg', 'second.jpg']);
});

it('creates a text entities project with the service’s task name', async () => {
  render(<NewProjectPage />);
  fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Reports' } });
  fireEvent.click(screen.getByRole('button', { name: /^Text/ }));
  fireEvent.click(screen.getByRole('button', { name: /Named entities/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Create project' }));
  await waitFor(() => expect(calls.create).toHaveBeenCalledTimes(1));
  const payload = JSON.parse(calls.create.mock.calls[0][1].body);
  expect(payload).toMatchObject({ modality: 'text', task_type: 'ENTITY_EXTRACTION' });
  expect(calls.navigate).toHaveBeenCalledWith({ id: 'project', projectId: 'created-project', tab: 'overview' });
});
