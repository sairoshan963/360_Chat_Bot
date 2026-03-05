import { useEffect, useState, useCallback } from 'react';
import {
  Card, Typography, Space, Button, message, Alert, Upload,
  Input, Select, Tabs, Tag, Avatar, Table,
} from 'antd';
import { UploadOutlined, DownloadOutlined, ApartmentOutlined, UnorderedListOutlined } from '@ant-design/icons';
import usePageTitle from '../../hooks/usePageTitle';
import {
  ReactFlow, Background, Controls, MiniMap,
  Handle, Position, useNodesState, useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { getOrgHierarchy, importOrg } from '../../api/users';

const { Title } = Typography;

const ROLE_TAG_COLOR  = { SUPER_ADMIN: 'red', HR_ADMIN: 'blue', MANAGER: 'green', EMPLOYEE: 'default' };
const ROLE_AVATAR_BG  = { SUPER_ADMIN: '#ff4d4f', HR_ADMIN: '#1677ff', MANAGER: '#52c41a', EMPLOYEE: '#8c8c8c' };

const NODE_W = 230;
const NODE_H = 96;

function applyDagreLayout(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 70, marginx: 30, marginy: 30 });
  g.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const { x, y } = g.node(n.id);
    return { ...n, position: { x: x - NODE_W / 2, y: y - NODE_H / 2 } };
  });
}

function OrgNode({ data }) {
  const initials = `${data.first_name?.[0] ?? ''}${data.last_name?.[0] ?? ''}`.toUpperCase();
  return (
    <div style={{ width: NODE_W, background: '#fff', borderRadius: 10, border: '1px solid #e8e8e8', boxShadow: '0 2px 10px rgba(0,0,0,.08)', padding: '10px 14px' }}>
      <Handle type="target" position={Position.Top}    style={{ background: '#d9d9d9', width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: '#d9d9d9', width: 8, height: 8 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Avatar size={40} style={{ background: ROLE_AVATAR_BG[data.role], flexShrink: 0, fontWeight: 700, fontSize: 14 }}>{initials}</Avatar>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {[data.first_name, data.middle_name, data.last_name].filter(Boolean).join(' ')}
          </div>
          <div style={{ fontSize: 11, color: '#888', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: 5 }}>
            {data.email}
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            <Tag color={ROLE_TAG_COLOR[data.role]} style={{ fontSize: 10, lineHeight: '16px', padding: '0 5px', margin: 0 }}>
              {data.role.replace('_', ' ')}
            </Tag>
            {data.department && (
              <Tag style={{ fontSize: 10, lineHeight: '16px', padding: '0 5px', margin: 0, color: '#555' }}>{data.department}</Tag>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const nodeTypes = { org: OrgNode };

const CSV_TEMPLATE = `email,first_name,middle_name,last_name,role,department
alice@gamyam.com,Alice,,Smith,EMPLOYEE,Engineering
bob@gamyam.com,Bob,,Jones,MANAGER,Engineering`;

export default function OrgPage() {
  usePageTitle('Organisation');
  const [org,        setOrg]        = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [importing,  setImporting]  = useState(false);
  const [search,     setSearch]     = useState('');
  const [deptFilter, setDeptFilter] = useState(null);
  const [activeTab,  setActiveTab]  = useState('diagram');

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getOrgHierarchy();
      setOrg(res.data.hierarchy || []);
    } catch { message.error('Failed to load org hierarchy'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!org.length) return;
    let filtered = org;
    if (deptFilter) filtered = filtered.filter((u) => u.department === deptFilter);
    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter((u) =>
        `${u.first_name || ''} ${u.middle_name || ''} ${u.last_name || ''}`.toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q)
      );
    }
    const visibleIds = new Set(filtered.map((u) => u.id));
    const rawNodes = filtered.map((u) => ({ id: String(u.id), type: 'org', data: u, position: { x: 0, y: 0 } }));
    const rawEdges = filtered
      .filter((u) => u.manager_id && visibleIds.has(u.manager_id))
      .map((u) => ({
        id: `e-${u.manager_id}-${u.id}`,
        source: String(u.manager_id),
        target: String(u.id),
        style: { stroke: '#bfbfbf', strokeWidth: 1.5 },
      }));
    const laidOut = applyDagreLayout(rawNodes, rawEdges);
    setNodes(laidOut);
    setEdges(rawEdges);
  }, [org, search, deptFilter]);

  const departments = [...new Set(org.map((u) => u.department).filter(Boolean))].sort();

  const handleImport = ({ file }) => {
    const reader = new FileReader();
    reader.onload = async (e) => {
      setImporting(true);
      try {
        const res = await importOrg(e.target.result);
        message.success(`Imported ${res.data.imported} user(s)`);
        load();
      } catch (err) {
        message.error(err.response?.data?.message || 'Import failed');
      } finally { setImporting(false); }
    };
    reader.readAsText(file);
    return false;
  };

  const downloadTemplate = () => {
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([CSV_TEMPLATE], { type: 'text/csv' })),
      download: 'org_import_template.csv',
    });
    a.click();
  };

  const listColumns = [
    {
      title: 'Employee',
      render: (_, r) => (
        <Space>
          <Avatar size={32} style={{ background: ROLE_AVATAR_BG[r.role], fontSize: 12, fontWeight: 700 }}>
            {`${r.first_name?.[0] ?? ''}${r.last_name?.[0] ?? ''}`.toUpperCase()}
          </Avatar>
          <span style={{ fontWeight: 500 }}>{[r.first_name, r.middle_name, r.last_name].filter(Boolean).join(' ')}</span>
        </Space>
      ),
    },
    { title: 'Email',      dataIndex: 'email' },
    { title: 'Department', dataIndex: 'department', render: (v) => v || '—' },
    { title: 'Role',       dataIndex: 'role', render: (v) => <Tag color={ROLE_TAG_COLOR[v]}>{v.replace('_', ' ')}</Tag> },
    { title: 'Reports To', dataIndex: 'manager_id', render: (mid) => { const m = org.find((u) => u.id === mid); return m ? [m.first_name, m.middle_name, m.last_name].filter(Boolean).join(' ') : '—'; } },
    { title: 'Status',     dataIndex: 'status', render: (v) => <Tag color={v === 'ACTIVE' ? 'green' : 'default'}>{v}</Tag> },
  ];

  const toolbar = (
    <Space wrap>
      <Input placeholder="Search by name or email" value={search} onChange={(e) => setSearch(e.target.value)} allowClear style={{ width: 220 }} />
      <Select placeholder="Filter by Department" value={deptFilter} onChange={setDeptFilter} allowClear style={{ width: 180 }}>
        {departments.map((d) => <Select.Option key={d} value={d}>{d}</Select.Option>)}
      </Select>
    </Space>
  );

  const importCard = (
    <Card size="small" style={{ marginBottom: 16 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <Space>
          <Button icon={<DownloadOutlined />} size="small" onClick={downloadTemplate}>Download CSV Template</Button>
          <Upload beforeUpload={() => false} accept=".csv" showUploadList={false} onChange={({ file }) => handleImport({ file: file.originFileObj || file })}>
            <Button type="primary" icon={<UploadOutlined />} size="small" loading={importing}>Import CSV</Button>
          </Upload>
        </Space>
        <Alert message="CSV: email, first_name, middle_name (optional), last_name, role, department (optional)" type="info" showIcon style={{ padding: '2px 10px', fontSize: 12 }} />
      </Space>
    </Card>
  );

  return (
    <Space direction="vertical" size={0} style={{ width: '100%' }}>
      <Card style={{ marginBottom: 16 }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
          <Title level={4} style={{ margin: 0 }}>
            Org Hierarchy &nbsp;<Tag color="blue" style={{ fontSize: 12, fontWeight: 500 }}>{org.length} people</Tag>
          </Title>
          {toolbar}
        </Space>
      </Card>

      <Card styles={{ body: { padding: 0 } }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ padding: '0 16px' }} items={[
          {
            key: 'diagram',
            label: <Space><ApartmentOutlined />Diagram</Space>,
            children: (
              <div>
                <div style={{ height: 620, width: '100%' }}>
                  <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                    nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.2} maxZoom={1.5}
                    nodesDraggable={false} defaultEdgeOptions={{ type: 'smoothstep' }} proOptions={{ hideAttribution: true }}>
                    <Background color="#f0f0f0" gap={16} />
                    <Controls />
                    <MiniMap nodeColor={(n) => ROLE_AVATAR_BG[n.data?.role] ?? '#8c8c8c'} style={{ background: '#fafafa' }} />
                  </ReactFlow>
                </div>
                <div style={{ padding: '10px 16px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  {Object.entries(ROLE_TAG_COLOR).map(([role, color]) => (
                    <Space key={role} size={4}>
                      <Avatar size={14} style={{ background: ROLE_AVATAR_BG[role] }} />
                      <span style={{ fontSize: 12, color: '#555' }}>{role.replace('_', ' ')}</span>
                    </Space>
                  ))}
                </div>
              </div>
            ),
          },
          {
            key: 'list',
            label: <Space><UnorderedListOutlined />List</Space>,
            children: (
              <div style={{ padding: '0 0 16px' }}>
                {importCard}
                <Table rowKey="id" columns={listColumns} loading={loading} pagination={{ pageSize: 20 }} size="middle"
                  dataSource={org.filter((u) => {
                    if (deptFilter && u.department !== deptFilter) return false;
                    if (search) {
                      const q = search.toLowerCase();
                      return `${u.first_name || ''} ${u.middle_name || ''} ${u.last_name || ''}`.toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q);
                    }
                    return true;
                  })}
                />
              </div>
            ),
          },
        ]} />
      </Card>
    </Space>
  );
}
