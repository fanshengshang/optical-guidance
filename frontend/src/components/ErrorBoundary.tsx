import { Component, type ReactNode } from 'react'
import { Button, Result } from 'antd'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * 页面级错误边界：懒加载 chunk 加载失败、或某个页面组件在特定数据/环境下渲染抛异常时，
 * 没有 boundary 的话 React 会卸载整棵树 → 整屏白屏（连侧边栏都没了）。
 * 这里只兜住内容区，出错时显示可读信息 + 重试，侧边栏仍可点其他菜单。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: unknown) {
    console.error('[ErrorBoundary] 页面渲染出错:', error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title="页面加载或渲染出错"
          subTitle={
            <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {this.state.error.message || String(this.state.error)}
            </span>
          }
          extra={
            <Button type="primary" onClick={this.reset}>
              重试
            </Button>
          }
        />
      )
    }
    return this.props.children
  }
}
