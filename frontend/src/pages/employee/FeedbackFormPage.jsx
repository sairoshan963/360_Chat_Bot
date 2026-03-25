import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Form, Button, Typography, Space, Tag, Input,
  Slider, Collapse, Progress, message, Spin, Popconfirm, Divider, Alert,
} from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { getTask, saveDraft, submitTask } from '../../api/tasks';
import usePageTitle from '../../hooks/usePageTitle';
import {
  getStandardRatingLabel,
  getStandardRatingSliderMarks,
  isStandardFivePointScale,
} from '../../utils/ratingLabels';

const { Title, Text } = Typography;
const { Panel }       = Collapse;
const { TextArea }    = Input;

function QuestionField({ question, value, onChange, readOnly }) {
  const { type, question_text, is_required, rating_scale_min, rating_scale_max } = question;
  const label = <>{question_text}{is_required && <Text type="danger"> *</Text>}</>;

  if (type === 'RATING') {
    const min = rating_scale_min || 1;
    const max = rating_scale_max || 5;
    const useLabels = isStandardFivePointScale(min, max);
    const marks = useLabels
      ? getStandardRatingSliderMarks()
      : { [min]: String(min), [max]: String(max) };
    const labelText = value != null && useLabels ? getStandardRatingLabel(value) : null;
    return (
      <Form.Item label={label} help={`${min} = lowest · ${max} = highest`} style={{ marginBottom: 20 }}>
        <Space direction="vertical" size={12} style={{ width: '100%', maxWidth: 520 }}>
          <div style={{ padding: useLabels ? '8px 4px 0' : 0 }}>
            <Slider
              min={min}
              max={max}
              step={1}
              value={value ?? undefined}
              onChange={readOnly ? undefined : onChange}
              disabled={readOnly}
              marks={marks}
              style={{ minWidth: 280 }}
            />
          </div>
          {value != null && (
            <Tag color="blue" style={{ fontSize: 15, padding: '4px 12px', alignSelf: 'flex-start' }}>
              {labelText != null ? `${value} — ${labelText}` : String(value)}
            </Tag>
          )}
        </Space>
      </Form.Item>
    );
  }
  return (
    <Form.Item label={label} style={{ marginBottom: 20 }}>
      <TextArea rows={3} value={value || ''} onChange={readOnly ? undefined : (e) => onChange(e.target.value)}
        placeholder="Your response…" readOnly={readOnly} />
    </Form.Item>
  );
}

export default function FeedbackFormPage() {
  usePageTitle('Feedback Form');
  const { id: taskId } = useParams();
  const navigate       = useNavigate();

  const [task,       setTask]       = useState(null);
  const [answers,    setAnswers]    = useState({});
  const [loading,    setLoading]    = useState(true);
  const [saving,     setSaving]     = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setLoading(true);
    getTask(taskId).then((r) => {
      const t = r.data.task;
      setTask(t);
      const restored = {};
      const source = ['SUBMITTED','LOCKED'].includes(t.status) && t.submitted_answers?.length
        ? t.submitted_answers
        : t.draft_answers?.length ? t.draft_answers : [];
      for (const a of source) {
        if (a.question_id) restored[a.question_id] = a.rating_value != null ? a.rating_value : (a.text_value ?? undefined);
      }
      setAnswers(restored);
    }).catch(() => message.error('Failed to load task')).finally(() => setLoading(false));
  }, [taskId]);

  const setAnswer = (qId, value) => setAnswers((prev) => ({ ...prev, [qId]: value }));

  const buildPayload = (allSections) => {
    const result = [];
    for (const sec of allSections) {
      for (const q of (sec.questions || []).filter(Boolean)) {
        const val = answers[q.id];
        if (val === undefined || val === null || val === '') continue;
        result.push(q.type === 'RATING' ? { question_id: q.id, rating_value: Number(val) } : { question_id: q.id, text_value: String(val) });
      }
    }
    return result;
  };

  const handleSaveDraft = useCallback(async () => {
    const sections = task?.template?.sections || [];
    setSaving(true);
    try {
      await saveDraft(taskId, { answers: buildPayload(sections) });
      message.success('Draft saved');
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.detail || 'Failed to save draft');
    } finally { setSaving(false); }
  }, [task, taskId, answers]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = async () => {
    if (submitting) return;  // prevent double-submit from rapid Popconfirm clicks
    const sections = task?.template?.sections || [];
    for (const sec of sections) {
      for (const q of (sec.questions || []).filter(Boolean)) {
        if (q.is_required) {
          const v = answers[q.id];
          if (v === undefined || v === null || v === '') { message.error(`Required: "${q.question_text?.slice(0, 60)}"`); return; }
        }
      }
    }
    const payload = buildPayload(sections);
    if (!payload.length) { message.error('Please answer at least one question'); return; }
    setSubmitting(true);
    try {
      await submitTask(taskId, payload);
      message.success('Feedback submitted!');
      navigate('/employee/tasks');
    } catch (err) {
      message.error(err.response?.data?.message || err.response?.data?.detail || 'Submission failed');
    } finally { setSubmitting(false); }
  };

  if (loading) return <Spin style={{ display: 'block', marginTop: 80 }} />;
  if (!task)   return null;

  const sections     = task.template?.sections || [];
  const allQuestions = sections.flatMap((s) => (s.questions || []).filter(Boolean));
  const answered     = allQuestions.filter((q) => { const v = answers[q.id]; return v !== undefined && v !== null && v !== ''; }).length;
  const pct        = allQuestions.length ? Math.round((answered / allQuestions.length) * 100) : 0;
  const isReadOnly = task.status === 'SUBMITTED' || task.status === 'LOCKED';

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {!isReadOnly && (
        <Alert type="info" showIcon icon={<SaveOutlined />}
          message={task.draft_answers?.length
            ? 'Your previously saved draft answers have been restored. Use "Save Draft" anytime to keep your progress.'
            : 'Use "Save Draft" to save your progress. Your answers will be stored on the server and restored if you return later.'} />
      )}
      <Card>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <div>
            <Title level={4} style={{ margin: 0 }}>Feedback for {task.reviewee_first} {task.reviewee_last}</Title>
            <Space style={{ marginTop: 4 }}>
              <Tag color="blue">{task.reviewer_type}</Tag>
              <Tag color={task.status === 'SUBMITTED' ? 'green' : 'default'}>{task.status}</Tag>
              <Text type="secondary">{task.cycle_name}</Text>
            </Space>
          </div>
          {!isReadOnly && (
            <Space>
              <Button onClick={handleSaveDraft} loading={saving}>Save Draft</Button>
              <Popconfirm title="Submit feedback?" description="Once submitted, you cannot make changes." onConfirm={handleSubmit}>
                <Button type="primary" loading={submitting}>Submit Feedback</Button>
              </Popconfirm>
            </Space>
          )}
          {isReadOnly && <Tag color="green" style={{ fontSize: 14 }}>Submitted — Read Only</Tag>}
        </Space>
        <Divider style={{ margin: '12px 0' }} />
        <Space>
          <Text type="secondary">Completion:</Text>
          <Progress percent={pct} style={{ width: 200 }} size="small" />
          <Text type="secondary">{answered}/{allQuestions.length} answered</Text>
        </Space>
      </Card>

      <Collapse defaultActiveKey={sections.map((s) => s.id)} accordion={false}>
        {sections.map((section) => (
          <Panel key={section.id} header={<Text strong>{section.title}</Text>}>
            <Form layout="vertical">
              {(section.questions || []).filter(Boolean).map((q) => (
                <QuestionField key={q.id} question={q} value={answers[q.id]} onChange={(v) => setAnswer(q.id, v)} readOnly={isReadOnly} />
              ))}
            </Form>
          </Panel>
        ))}
      </Collapse>

      {!isReadOnly && (
        <Card>
          <Space>
            <Button onClick={handleSaveDraft} loading={saving}>Save Draft</Button>
            <Popconfirm title="Submit feedback?" description="Once submitted, you cannot make changes." onConfirm={handleSubmit}>
              <Button type="primary" loading={submitting}>Submit Feedback</Button>
            </Popconfirm>
            <Button onClick={() => navigate(-1)}>Back</Button>
          </Space>
        </Card>
      )}
    </Space>
  );
}
